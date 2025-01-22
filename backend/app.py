from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from urllib.parse import unquote
from playwright.async_api import async_playwright
import json
import time
from typing import Dict, List, Optional
import re
import openai
import logging
import os
from dotenv import load_dotenv
from pydantic import BaseModel

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="AI Review Scraper",
    description="API for scraping reviews from websites",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Get OpenAI API key from environment
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
if not OPENAI_API_KEY:
    raise EnvironmentError("OpenAI API key not found in environment variables")

openai.api_key = OPENAI_API_KEY

# Update the Review model to match frontend expectations
class Review(BaseModel):
    title: str
    body: str  # This will contain the review text
    rating: Optional[float]  # This matches the frontend's rating field
    reviewer: str  # This matches the frontend's reviewer field

class ReviewResponse(BaseModel):
    reviews_count: int
    reviews: List[Review]  # Frontend expects this to be "reviews" not "review_list"
    pages_with_unique_reviews: int
    url: str
    scrape_date: str

async def check_page_type(page) -> str:
    """Check the type of pagination used on the page."""
    patterns = {
        'infinite_scroll': [
            'window.addEventListener("scroll"',
            'IntersectionObserver',
            'infinite',
            'loadMore'
        ],
        'button': [
            '.next',
            '.Next',
            '[class*="pagination"] button',
            'button[class*="next"]',
            'a[class*="next"]'
        ],
        'numbered': [
            '.pagination',
            '[class*="pagination"]',
            'nav[role="navigation"]'
        ],
        'url': [
            'a[href*="page="]',
            'a[href*="/page/"]',
            'link[rel="next"]'
        ]
    }
    
    for ptype, selectors in patterns.items():
        for selector in selectors:
            try:
                if selector.startswith('.') or selector.startswith('['):
                    elements = await page.query_selector_all(selector)
                    if elements:
                        return ptype
                else:
                    content = await page.content()
                    if selector in content.lower():
                        return ptype
            except Exception as e:
                logger.error(f"Error checking page type: {str(e)}")
                continue
    
    return 'unknown'

async def scroll_and_load(page):
    """Handle dynamic content loading through scrolling and buttons."""
    try:
        # First, wait for review widget to load
        try:
            await page.wait_for_selector('.jdgm-review-widget, [data-reviews-content]', timeout=5000)
        except Exception:
            logger.info("No review widget found")

        # Scroll multiple times to trigger lazy loading
        current_height = 0
        for _ in range(5):  # Increased from 3 to 5 scrolls
            try:
                await page.evaluate('''() => {
                    window.scrollTo({
                        top: document.body.scrollHeight,
                        behavior: 'smooth'
                    });
                }''')
                await page.wait_for_timeout(2000)  # Reduced from 3000 to 2000ms
                
                new_height = await page.evaluate('document.body.scrollHeight')
                if new_height == current_height:
                    break
                current_height = new_height
            except Exception as scroll_error:
                logger.error(f"Scroll error: {str(scroll_error)}")
                break
        
        # Try clicking "Load More" buttons with additional selectors for Bhumi
        load_more_selectors = [
            'button:text-is("Show More")',
            'button:text-is("Load More")',
            'button:text-is("More Reviews")',
            '.jdgm-rev-widg__load-more-btn',  # Judge.me specific
            '[data-load-more-reviews]',
            '[class*="load-more"]',
            '[class*="show-more"]',
            '[class*="LoadMore"]'
        ]
        
        for selector in load_more_selectors:
            try:
                while True:
                    more_btn = await page.query_selector(selector)
                    if not more_btn or not await more_btn.is_visible():
                        break
                    
                    # Scroll button into view
                    await more_btn.scroll_into_view_if_needed()
                    await page.wait_for_timeout(1000)
                    
                    # Click and wait for new content
                    await more_btn.click()
                    await page.wait_for_timeout(2000)
                    
                    # Wait for network to be idle
                    try:
                        await page.wait_for_load_state('networkidle', timeout=5000)
                    except:
                        pass
            except Exception:
                continue
                
    except Exception as e:
        logger.error(f"Error in dynamic loading: {str(e)}")

    # Final wait to ensure all content is loaded
    await page.wait_for_timeout(2000)

async def handle_pagination(page, curr_page: int) -> bool:
    """Handle different types of pagination."""
    try:
        selectors = [
            f'[class*="pagination"] [aria-label="Page {curr_page + 1}"]',
            f'[class*="pagination"] a:text("{curr_page + 1}")',
            f'button:text("{curr_page + 1}")',
            f'a[href*="page={curr_page + 1}"]',
            '[class*="pagination"] [aria-label*="next"]',
            '[class*="pagination"] button:has-text(">")',
            '[class*="pagination"] a:has-text(">")',
            '.next a',
            'a[rel="next"]',
            '.pagination__next',
            '.pagination__item--next',
            '[class*="pagination"] button:not([disabled])',
            '[class*="pagination"] a:not([class*="disabled"])',
            'li.next a'
        ]

        for selector in selectors:
            try:
                try:
                    await page.wait_for_selector(selector, timeout=5000)
                except:
                    continue

                next_btn = await page.query_selector(selector)
                if next_btn and await next_btn.is_visible():
                    before_url = page.url
                    before_html = await page.content()
                    
                    await next_btn.scroll_into_view_if_needed()
                    await page.wait_for_timeout(1000)
                    
                    try:
                        await next_btn.click(timeout=5000)
                    except:
                        await page.evaluate('(element) => element.click()', next_btn)
                    
                    try:
                        await page.wait_for_load_state('networkidle', timeout=5000)
                    except:
                        await page.wait_for_timeout(2000)
                    
                    after_url = page.url
                    after_html = await page.content()
                    
                    if before_url != after_url or before_html != after_html:
                        return True
                
            except Exception as e:
                continue
        
        try:
            current_url = page.url            
            if 'page=' in current_url:
                next_url = re.sub(r'page=\d+', f'page={curr_page + 1}', current_url)
            else:
                separator = '&' if '?' in current_url else '?'
                next_url = f"{current_url}{separator}page={curr_page + 1}"
            
            response = await page.goto(next_url)
            if response and response.ok():
                await page.wait_for_timeout(2000)
                return True
        
        except Exception as e:
            pass
        
        return False
        
    except Exception as e:
        return False

async def grab_reviews(page) -> List[Dict]:
    """Get reviews from the current page."""
    # First, wait for reviews to load
    try:
        await page.wait_for_selector('[data-reviews-content], .jdgm-rev', timeout=5000)
    except Exception:
        logger.info("No reviews container found with default selector")

    reviews = await page.evaluate("""() => {
        function cleanText(text) {
            if (!text) return '';
            text = text.replace(/\\s+/g, ' ')
                      .replace(/\\r?\\n/g, ' ')
                      .trim();
            text = text.split(/(?:read more|show more|see more)/i)[0];
            
            const words = text.split(' ');
            let cleanedText = '';
            let lastPhrase = '';
            
            for (let i = 0; i < words.length; i++) {
                const currentPhrase = words.slice(i, i + 3).join(' ');
                if (cleanedText.includes(currentPhrase) && currentPhrase.split(' ').length > 2) {
                    continue;
                }
                if (cleanedText) {
                    cleanedText += ' ';
                }
                cleanedText += words[i];
                lastPhrase = currentPhrase;
            }
            
            return cleanedText.trim();
        }
        
        function getStars(element) {
            try {
                let stars = null;
                
                // Judge.me specific selectors
                const jdgmRating = element.querySelector('.jdgm-rev__rating');
                if (jdgmRating) {
                    const dataScore = jdgmRating.getAttribute('data-score');
                    if (dataScore) {
                        stars = parseFloat(dataScore);
                        if (stars >= 0 && stars <= 5) return stars;
                    }
                }
                
                // General star selectors
                const star_elems = element.querySelectorAll(
                    '[class*="star-full"], [class*="star"][class*="filled"], .spr-icon-star, [class*="yotpo-star-full"], [class*="rating"] .full, .jdgm-star.jdgm--on'
                );
                if (star_elems.length > 0) {
                    stars = star_elems.length;
                    if (stars >= 0 && stars <= 5) {
                        return stars;
                    }
                }

                const dataAttrs = ['data-rating', 'data-score', 'data-stars', 'data-value'];
                for (const attr of dataAttrs) {
                    const value = element.getAttribute(attr);
                    if (value && !isNaN(value)) {
                        stars = parseFloat(value);
                        if (stars >= 0 && stars <= 5) {
                            return stars;
                        }
                    }
                }
                
                const fullText = element.textContent || '';
                const patterns = [
                    /([1-5]([.,]\\d)?)\s*(?:star|\/\s*5|$)/i,
                    /Rated\s+([1-5]([.,]\\d)?)/i,
                    /Rating:\s*([1-5]([.,]\\d)?)/i,
                    /([★⭐✩✭]{1,5})/
                ];

                for (const pattern of patterns) {
                    const match = fullText.match(pattern);
                    if (match) {
                        if (match[1].includes('★') || match[1].includes('⭐')) {
                            stars = match[1].length;
                        } else {
                            stars = parseFloat(match[1].replace(',', '.'));
                        }
                        if (stars >= 0 && stars <= 5) {
                            return stars;
                        }
                    }
                }

                return null;
            } catch (error) {
                return null;
            }
        }

        function isValid(text) {
            if (!text) return false;
            
            const invalidPatterns = [
                /^reviews?$/i,
                /^write a review$/i,
                /^see reviews?$/i,
                /^\d+\s+reviews?$/i,
                /^verified\s+/i,
                /^published/i,
                /^see more/i,
                /^read more/i,
                /^showing/i,
                /^customer reviews?$/i
            ];
            
            if (invalidPatterns.some(pattern => pattern.test(text.trim()))) {
                return false;
            }
            
            return text.trim().split(/\\s+/).length >= 3;
        }

        const review_boxes = document.querySelectorAll(
            '.review-item, .review-content, [data-review-id], [class*="review-container"], [class*="review_container"], .jdgm-rev, .yotpo-review, .spr-review, .stamped-review, .loox-review, .reviewsio-review, .okendo-review, .trustpilot-review, [data-reviews-target], [class*="ReviewCard"], [class*="review-card"], [data-review], .okeReviews-review-item, .jdgm-review-widget--reviews > div'
        );

        const seen = new Set();
        const found = [];

        Array.from(review_boxes).forEach(box => {
            const titleSelectors = [
                '[class*="review-title"]',
                '[class*="review_title"]',
                '[class*="ReviewTitle"]',
                '[class*="review-header"]',
                'h3', 'h4',
                '.review-title',
                '.jdgm-rev__title'
            ].join(',');

            const textSelectors = [
                '[class*="review-content"]',
                '[class*="review-body"]',
                '[class*="review_content"]',
                '[class*="ReviewContent"]',
                '[class*="review-text"]',
                '.jdgm-rev__body',
                '.yotpo-review-content',
                '.spr-review-content-body',
                '[class*="ReviewText"]',
                'p'
            ].join(',');

            const userSelectors = [
                '[class*="review-author"]',
                '[class*="reviewer-name"]',
                '[class*="author"]',
                '[class*="customer-name"]',
                '.jdgm-rev__author',
                '.yotpo-user-name',
                '.spr-review-header-byline',
                '[class*="ReviewAuthor"]'
            ].join(',');

            const title = cleanText(box.querySelector(titleSelectors)?.textContent);
            let text = cleanText(box.querySelector(textSelectors)?.textContent);

            if (!text) {
                const clone = box.cloneNode(true);
                const elementsToRemove = [
                    'button', 'input', 'select', 'option',
                    '[class*="more"]', '[class*="truncate"]',
                    '[class*="toggle"]', '[class*="expand"]',
                    'script', 'style', '[aria-hidden="true"]'
                ].join(',');
                
                Array.from(clone.querySelectorAll(elementsToRemove)).forEach(el => el.remove());
                text = cleanText(clone.textContent);
                
                if (text.length < 10) {
                    const mainContent = box.querySelector('[class*="content"], [class*="body"], [class*="text"]');
                    if (mainContent) {
                        text = cleanText(mainContent.textContent);
                    }
                }
            }

            const user_name = cleanText(box.querySelector(userSelectors)?.textContent) || 'Anonymous';
            const stars = getStars(box);

            if (isValid(text) && !seen.has(text)) {
                seen.add(text);
                found.push({
                    title: title || "Review",
                    body: text,
                    rating: stars,
                    reviewer: user_name
                });
            }
        });

        return found;
    }""")
    
    # Clean up and validate reviews
    cleaned = []
    for review in reviews:
        if review.get('body') and len(review['body'].split()) >= 3:
            try:
                cleaned_review = {
                    'title': str(review.get('title', 'Review')),
                    'body': str(review['body']),
                    'rating': float(review['rating']) if review.get('rating') is not None else None,
                    'reviewer': str(review.get('reviewer', 'Anonymous'))
                }
                
                if cleaned_review['rating'] is not None:
                    if not (0 <= cleaned_review['rating'] <= 5):
                        cleaned_review['rating'] = None
                        
                cleaned.append(cleaned_review)
                
            except Exception as e:
                logger.error(f"Error cleaning review: {str(e)}")
                continue
    
    # Get AI selectors
    html_content = await page.content()
    
    # Get AI selectors
    prompt = f"""Find CSS selectors for reviews in this HTML.
    Look for:
    1. Review container selectors
    2. Review text selectors
    3. Star rating selectors
    
    Return ONLY selectors like this:
    CONTAINERS: [selector1, selector2]
    CONTENT: [selector1, selector2]
    RATINGS: [selector1, selector2]
    """
    
    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You're an expert at finding CSS selectors for reviews."},
            {"role": "user", "content": prompt},
            {"role": "user", "content": html_content[:15000]}
        ],
        temperature=0.1
    )
    
    result = response['choices'][0]['message']['content']
    
    # Parse selectors
    containers = []
    content = []
    ratings = []
    
    current_list = None
    for line in result.split('\n'):
        if 'CONTAINERS:' in line:
            current_list = containers
            line = line.split('CONTAINERS:')[1]
        elif 'CONTENT:' in line:
            current_list = content
            line = line.split('CONTENT:')[1]
        elif 'RATINGS:' in line:
            current_list = ratings
            line = line.split('RATINGS:')[1]
            
        if current_list is not None:
            selectors = re.findall(r'[\'"]([^\'"]+)[\'"]', line)
            current_list.extend(selectors)

    # Try AI selectors
    ai_reviews = await page.evaluate("""(selectors) => {
        const found = [];
        const seen = new Set();
        
        for (const containerSelector of selectors.containers) {
            document.querySelectorAll(containerSelector).forEach(box => {
                for (const contentSelector of selectors.content) {
                    const textEl = box.querySelector(contentSelector);
                    if (!textEl) continue;
                    
                    const text = (textEl.textContent || '').trim();
                    if (!text || text.length < 10 || seen.has(text)) continue;
                    
                    let stars = null;
                    for (const ratingSelector of selectors.ratings) {
                        const ratingEl = box.querySelector(ratingSelector);
                        if (!ratingEl) continue;
                        
                        const match = ratingEl.textContent.match(/([1-5]([.,]\\d)?)/);
                        if (match) {
                            stars = parseFloat(match[1]);
                            break;
                        }
                    }
                    
                    seen.add(text);
                    found.push({
                        title: "Review",
                        body: text,
                        rating: stars,
                        reviewer: "Anonymous"
                    });
                }
            });
        }
        
        return found;
    }""", {"containers": containers, "content": content, "ratings": ratings})
    
    # Add AI reviews to cleaned reviews
    seen_text = set(review['body'] for review in cleaned)
    
    for review in ai_reviews:
        if review['body'] not in seen_text:
            try:
                cleaned_review = {
                    'title': str(review.get('title', 'Review')),
                    'body': str(review['body']),
                    'rating': float(review['rating']) if review.get('rating') is not None else None,
                    'reviewer': str(review.get('reviewer', 'Anonymous'))
                }
                
                if cleaned_review['rating'] is not None:
                    if not (0 <= cleaned_review['rating'] <= 5):
                        cleaned_review['rating'] = None
                        
                cleaned.append(cleaned_review)
                seen_text.add(cleaned_review['body'])
                
            except Exception as e:
                logger.error(f"Error cleaning AI review: {str(e)}")
                continue
    
    return cleaned

def validate_review(review: dict) -> bool:
    """Validate a single review object."""
    try:
        # Check required fields
        if not isinstance(review.get('body', ''), str):
            logger.error(f"Invalid body type: {type(review.get('body'))}")
            return False
            
        if not isinstance(review.get('title', ''), str):
            logger.error(f"Invalid title type: {type(review.get('title'))}")
            return False
            
        if not isinstance(review.get('reviewer', ''), str):
            logger.error(f"Invalid reviewer type: {type(review.get('reviewer'))}")
            return False
            
        # Check rating
        rating = review.get('rating')
        if rating is not None:
            try:
                rating = float(rating)
                if not (0 <= rating <= 5):
                    logger.error(f"Rating out of range: {rating}")
                    return False
            except (ValueError, TypeError):
                logger.error(f"Invalid rating value: {rating}")
                return False
                
        return True
        
    except Exception as e:
        logger.error(f"Error validating review: {str(e)}")
        return False

async def scrape_site(url: str, max_count: int = 500) -> Dict:
    """Main function for scraping reviews."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()
        review_list = []
        successful_pages = 0
        
        try:
            logger.info(f"Loading page: {url}")
            await page.goto(url, wait_until='domcontentloaded')
            await page.wait_for_timeout(2000)
            
            curr_page = 1
            while len(review_list) < max_count and curr_page <= 1: # Only one page for now
                logger.info(f"Scraping page {curr_page}...")
                
                await scroll_and_load(page)
                new_reviews = await grab_reviews(page)
                
                # Validate new reviews
                valid_reviews = [review for review in new_reviews if validate_review(review)]
                logger.info(f"Found {len(valid_reviews)} valid reviews out of {len(new_reviews)} total")
                
                if valid_reviews:
                    existing_texts = set(r['body'] for r in review_list)
                    unique_reviews = [r for r in valid_reviews if r['body'] not in existing_texts]
                    
                    if unique_reviews:
                        successful_pages += 1
                        logger.info(f"Added {len(unique_reviews)} new unique reviews from page {curr_page}")
                        review_list.extend(unique_reviews)
                    else:
                        logger.info("No new unique reviews found. Stopping.")
                        break
                else:
                    logger.info("No valid reviews found on current page. Stopping.")
                    break

                if len(review_list) < max_count:
                    has_next = await handle_pagination(page, curr_page)
                    if not has_next:
                        break
                    curr_page += 1
                else:
                    break

            result = {
                "reviews_count": len(review_list),
                "reviews": review_list,
                "pages_with_unique_reviews": successful_pages,
                "url": url,
                "scrape_date": time.strftime("%Y-%m-%d")
            }
            
            logger.info(f"Final result: {len(review_list)} reviews from {successful_pages} pages")
            return result
            
        finally:
            await context.close()
            await browser.close()


@app.get("/api/reviews", response_model=ReviewResponse)
async def get_reviews(
    page: str = Query(..., description="URL to scrape reviews from"),
    max_count: int = Query(10000, ge=10, le=100000, description="Maximum number of reviews to scrape")
):
    try:
        url = unquote(page)
        logger.info(f"Starting review scrape for URL: {url}")
        
        try:
            result = await scrape_site(url, max_count)
            logger.info(f"Raw scrape result: {result}")
            
            # Validate result structure
            if not isinstance(result, dict):
                raise ValueError(f"Expected dict result, got {type(result)}")
            
            required_fields = ["reviews_count", "reviews", "pages_with_unique_reviews", "url", "scrape_date"]
            missing_fields = [field for field in required_fields if field not in result]
            if missing_fields:
                raise ValueError(f"Missing required fields: {missing_fields}")
            
            # Check reviews format
            if not isinstance(result["reviews"], list):
                raise ValueError(f"Expected reviews to be list, got {type(result['reviews'])}")
            
            # Create response using the model
            try:
                response_data = ReviewResponse(
                    reviews_count=result["reviews_count"],
                    reviews=[Review(**review) for review in result["reviews"]],
                    pages_with_unique_reviews=result["pages_with_unique_reviews"],
                    url=result["url"],
                    scrape_date=result["scrape_date"]
                )
                logger.info(f"Successfully created response with {response_data.reviews_count} reviews")
                return response_data
                
            except Exception as model_error:
                logger.error(f"Error creating response model: {str(model_error)}")
                logger.error(f"Result data: {result}")
                raise ValueError(f"Error creating response model: {str(model_error)}")
                
        except Exception as scrape_error:
            logger.error(f"Error during scraping: {str(scrape_error)}")
            raise ValueError(f"Scraping error: {str(scrape_error)}")
            
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
# Health check endpoint
@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/api/debug-reviews")
async def debug_reviews(page: str = Query(...)):
    url = unquote(page)
    result = await scrape_site(url)
    return {"raw_result": result}