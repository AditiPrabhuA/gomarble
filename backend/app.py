from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
from playwright.async_api import async_playwright
import json
from bs4 import BeautifulSoup
import time
from typing import Dict, List, Tuple, Optional
import re
import logging
from pydantic import BaseModel
from urllib.parse import unquote
import httpx
import uvicorn
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Review Scraper API",
    description="API for scraping reviews from websites with Ollama LLM-enhanced extraction",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ollama Configuration
OLLAMA_API_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "mistral"  # You can change this to any model you have pulled in Ollama

# Response Models
class Review(BaseModel):
    title: str
    body: str
    rating: Optional[float]
    reviewer: str

class ReviewResponse(BaseModel):
    reviews_count: int
    reviews: List[Review]
    pages_with_unique_reviews: int
    url: str
    scrape_date: str

async def query_ollama(prompt: str) -> str:
    """
    Query Ollama API for LLM responses.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                OLLAMA_API_URL,
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=30.0
            )
            
            if response.status_code == 200:
                return response.json()["response"]
            else:
                logger.error(f"Ollama API error: {response.status_code}")
                return ""
                
    except Exception as e:
        logger.error(f"Error querying Ollama: {str(e)}")
        return ""

async def detect_pagination_type(page) -> str:
    """Detect the type of pagination used on the page."""
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
                logger.error(f"Error detecting pagination type: {str(e)}")
                continue
    
    return 'unknown'
async def get_dynamic_selectors(html_content: str) -> Tuple[List[str], List[str], List[str]]:
    """Use Ollama to identify dynamic CSS selectors for reviews."""
    prompt = f"""Analyze this HTML and identify CSS selectors for review elements.
    Focus on finding:
    1. Review container selectors that contain individual reviews
    2. Review content/body selectors
    3. Rating/stars selectors
    
    Return only the selectors in this exact format:
    CONTAINERS: ["selector1", "selector2", ...]
    CONTENT: ["selector1", "selector2", ...]
    RATINGS: ["selector1", "selector2", ...]
    
    HTML Content:
    {html_content[:15000]}
    """
    
    try:
        result = await query_ollama(prompt)
        
        # Parse the response
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
        
        # Add fallback selectors if LLM didn't find enough
        if len(containers) < 2:
            containers.extend([
                '.review-item',
                '[data-review-id]',
                '[class*="review-container"]',
                '.jdgm-rev',
                '.yotpo-review'
            ])
        
        if len(content) < 2:
            content.extend([
                '[class*="review-content"]',
                '[class*="review-body"]',
                'p'
            ])
            
        if len(ratings) < 2:
            ratings.extend([
                '[class*="rating"]',
                '[class*="stars"]',
                '[data-rating]'
            ])
        
        return containers, content, ratings
        
    except Exception as e:
        logger.error(f"Error getting dynamic selectors: {str(e)}")
        return [], [], []

async def handle_dynamic_loading(page):
    """Handle dynamic content loading through scrolling and button clicks."""
    try:
        # Scroll to bottom in increments
        current_height = 0
        for _ in range(3):
            try:
                await page.evaluate('''() => {
                    window.scrollTo({
                        top: document.body.scrollHeight,
                        behavior: 'smooth'
                    });
                }''')
                # Increased wait time after scroll
                await page.wait_for_timeout(3000)
                
                new_height = await page.evaluate('document.body.scrollHeight')
                if new_height == current_height:
                    # Add extra wait when height doesn't change
                    await page.wait_for_timeout(2000)
                    break
                current_height = new_height
            except Exception as scroll_error:
                logger.error(f"Scroll error: {str(scroll_error)}")
                # Add wait after error before retrying
                await page.wait_for_timeout(2000)
                break
        
        # Add wait before trying to click buttons
        await page.wait_for_timeout(2000)
        
        # Try clicking "Load More" buttons
        load_more_selectors = [
            'button:text-is("Show More")',
            'button:text-is("Load More")',
            'a:text-is("Show More")',
            'a:text-is("Load More")',
            '[class*="load-more"]',
            '[class*="show-more"]'
        ]
        
        for selector in load_more_selectors:
            try:
                while True:
                    button = await page.query_selector(selector)
                    if not button or not await button.is_visible():
                        break
                    await button.click()
                    # Increased wait time after clicking load more
                    await page.wait_for_timeout(3000)
            except Exception as e:
                logger.error(f"Error clicking load more button: {str(e)}")
                continue
                
    except Exception as e:
        logger.error(f"Error in dynamic loading: {str(e)}")

async def handle_pagination(context, page, current_page: int) -> bool:
    """Handle different types of pagination including numbered buttons and arrows."""
    try:
        # First try direct numbered pagination
        selectors = [
            f'[class*="pagination"] [aria-label="Page {current_page + 1}"]',
            f'[class*="pagination"] a:text("{current_page + 1}")',
            f'button:text("{current_page + 1}")',
            f'a[href*="page={current_page + 1}"]',
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

        # Try to find and click pagination elements
        for selector in selectors:
            try:
                try:
                    await page.wait_for_selector(selector, timeout=5000)
                except:
                    continue

                element = await page.query_selector(selector)
                if element:
                    
                    if await element.is_visible():
                        before_url = page.url
                        before_html = await page.content()
                        
                        await element.scroll_into_view_if_needed()
                        await page.wait_for_timeout(1000)
                        
                        try:
                            await element.click(timeout=5000)
                            
                        except:
                            await page.evaluate('(element) => element.click()', element)
                            
                        
                        try:
                            await page.wait_for_load_state('networkidle', timeout=5000)
                        except:
                            await page.wait_for_timeout(2000)
                        
                        after_url = page.url
                        after_html = await page.content()
                        
                        if before_url != after_url or before_html != after_html:
                            logger.info(f"Successfully navigated to next page: {after_url}")
                            return True
                
            except Exception as e:
                logger.error(f"Error with selector {selector}: {str(e)}")
                continue
        
        # If clicking didn't work, try URL modification
        try:
            current_url = page.url
            logger.info("Trying URL modification...")
            
            # Check if the current URL already contains a page parameter
            if 'page=' in current_url:
                # Modify existing page parameter
                next_url = re.sub(r'page=\d+', f'page={current_page + 1}', current_url)
            else:
                # Add page parameter
                separator = '&' if '?' in current_url else '?'
                next_url = f"{current_url}{separator}page={current_page + 1}"
            
            logger.info(f"Attempting to navigate to: {next_url}")
            
            # Validate the URL before navigation
            try:
                parsed_url = urlparse(next_url)
                if not all([parsed_url.scheme, parsed_url.netloc]):
                    logger.error(f"Invalid URL: {next_url}")
                    return False
            except Exception as url_error:
                logger.error(f"URL parsing error: {url_error}")
                return False
            
            # Try to navigate to the new URL
            await page.goto(next_url, wait_until='domcontentloaded')
            await page.wait_for_timeout(2000)
            
            return True
        
        except Exception as e:
            logger.error(f"Error during URL modification: {str(e)}")
        
        logger.warning("No more pages found")
        return False
        
    except Exception as e:
        logger.error(f"Error in pagination: {str(e)}")
        return False

async def extract_reviews_traditional(page) -> List[Dict]:
    """Extract reviews using traditional selectors."""
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
        
        function extractRating(element) {
            try {
                let rating = null;
                
                const stars = element.querySelectorAll(
                    '[class*="star-full"], [class*="star"][class*="filled"], .spr-icon-star, [class*="yotpo-star-full"], [class*="rating"] .full'
                );
                if (stars.length > 0) {
                    rating = stars.length;
                    if (rating >= 0 && rating <= 5) {
                        return rating;
                    }
                }

                const dataAttrs = ['data-rating', 'data-score', 'data-stars', 'data-value'];
                for (const attr of dataAttrs) {
                    const value = element.getAttribute(attr);
                    if (value && !isNaN(value)) {
                        rating = parseFloat(value);
                        if (rating >= 0 && rating <= 5) {
                            return rating;
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
                            rating = match[1].length;
                        } else {
                            rating = parseFloat(match[1].replace(',', '.'));
                        }
                        if (rating >= 0 && rating <= 5) {
                            return rating;
                        }
                    }
                }

                return null;
            } catch (error) {
                console.error('Error extracting rating:', error);
                return null;
            }
        }

        function isValidReview(text) {
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

        const reviewSelectors = [
            '.review-item',
            '.review-content',
            '[data-review-id]',
            '[class*="review-container"]',
            '[class*="review_container"]',
            '.jdgm-rev',
            '.yotpo-review',
            '.spr-review',
            '.stamped-review',
            '.loox-review',
            '.reviewsio-review',
            '.okendo-review',
            '.trustpilot-review',
            '[data-reviews-target]',
            '[class*="ReviewCard"]',
            '[class*="review-card"]',
            '[data-review]',
            '.okeReviews-review-item'
        ].join(',');

        let reviewElements = Array.from(document.querySelectorAll(reviewSelectors));
        
        if (reviewElements.length === 0) {
            reviewElements = Array.from(document.querySelectorAll('*')).filter(el => {
                const text = (el.textContent || '').toLowerCase();
                const classes = (el.className || '').toLowerCase();
                const id = (el.id || '').toLowerCase();
                return (text.includes('review') || classes.includes('review') || id.includes('review')) &&
                       el.children && el.children.length > 0 &&
                       !text.match(/^(write|see|read|view)\s+reviews?$/i);
            });
        }

        const seenContent = new Set();
        const reviews = [];

        reviewElements.forEach(element => {
            const titleSelectors = [
                '[class*="review-title"]',
                '[class*="review_title"]',
                '[class*="ReviewTitle"]',
                '[class*="review-header"]',
                'h3', 'h4',
                '.review-title'
            ].join(',');

            const bodySelectors = [
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

            const reviewerSelectors = [
                '[class*="review-author"]',
                '[class*="reviewer-name"]',
                '[class*="author"]',
                '[class*="customer-name"]',
                '.jdgm-rev__author',
                '.yotpo-user-name',
                '.spr-review-header-byline',
                '[class*="ReviewAuthor"]'
            ].join(',');

            const title = cleanText(element.querySelector(titleSelectors)?.textContent);
            let body = cleanText(element.querySelector(bodySelectors)?.textContent);

            if (!body) {
                const clone = element.cloneNode(true);
                const elementsToRemove = [
                    'button', 'input', 'select', 'option',
                    '[class*="more"]', '[class*="truncate"]',
                    '[class*="toggle"]', '[class*="expand"]',
                    'script', 'style', '[aria-hidden="true"]'
                ].join(',');
                
                Array.from(clone.querySelectorAll(elementsToRemove)).forEach(el => el.remove());
                body = cleanText(clone.textContent);
                
                if (body.length < 10) {
                    const mainContent = element.querySelector('[class*="content"], [class*="body"], [class*="text"]');
                    if (mainContent) {
                        body = cleanText(mainContent.textContent);
                    }
                }
            }

            const reviewer = cleanText(element.querySelector(reviewerSelectors)?.textContent) || 'Anonymous';
            const rating = extractRating(element);

            if (isValidReview(body) && !seenContent.has(body)) {
                seenContent.add(body);
                reviews.push({
                    title: title || "Review",
                    body: body,
                    rating: rating,
                    reviewer: reviewer
                });
            }
        });

        return reviews;
    }""")
    
    # Clean up and validate reviews
    cleaned_reviews = []
    for review in reviews:
        if review['body'] and len(review['body'].split()) >= 3:
            if review['rating'] is not None:
                try:
                    review['rating'] = float(review['rating'])
                    if not (0 <= review['rating'] <= 5):
                        review['rating'] = None
                except (ValueError, TypeError):
                    review['rating'] = None
            cleaned_reviews.append(review)
    
    return cleaned_reviews

async def combine_extraction_methods(page) -> List[Dict]:
    """Combine traditional and LLM-based extraction methods."""
    all_reviews = []
    seen_content = set()
    
    # First, try traditional extraction
    traditional_reviews = await extract_reviews_traditional(page)
    for review in traditional_reviews:
        if review['body'] not in seen_content:
            seen_content.add(review['body'])
            all_reviews.append(review)
    
    # Then try LLM-based extraction
    try:
        html_content = await page.content()
        container_selectors, content_selectors, rating_selectors = await get_dynamic_selectors(html_content)
        
        llm_reviews = await page.evaluate("""(selectors) => {
            function cleanText(text) {
                if (!text) return '';
                return text.replace(/\\s+/g, ' ')
                          .replace(/\\r?\\n/g, ' ')
                          .trim()
                          .split(/(?:read more|show more|see more)/i)[0];
            }
            
            function extractRating(element, ratingSelectors) {
                for (const selector of ratingSelectors) {
                    const ratingEl = element.querySelector(selector);
                    if (ratingEl) {
                        const ratingText = ratingEl.textContent;
                        const ratingMatch = ratingText.match(/([1-5]([.,]\\d)?)/);
                        if (ratingMatch) {
                            return parseFloat(ratingMatch[1]);
                        }
                    }
                }
                return null;
            }
            
            const reviews = [];
            
            for (const containerSelector of selectors.containers) {
                const containers = document.querySelectorAll(containerSelector);
                containers.forEach(container => {
                    let content = null;
                    
                    for (const contentSelector of selectors.content) {
                        const contentEl = container.querySelector(contentSelector);
                        if (contentEl) {
                            content = cleanText(contentEl.textContent);
                            if (content) break;
                        }
                    }
                    
                    if (content && content.split(/\\s+/).length >= 3) {
                        const rating = extractRating(container, selectors.ratings);
                        reviews.push({
                            title: "Review",
                            body: content,
                            rating: rating,
                            reviewer: "Anonymous"
                        });
                    }
                });
            }
            
            return reviews;
        }""", {"containers": container_selectors, "content": content_selectors, "ratings": rating_selectors})
        
        for review in llm_reviews:
            if review['body'] not in seen_content:
                seen_content.add(review['body'])
                all_reviews.append(review)
                
    except Exception as e:
        logger.error(f"LLM extraction encountered an error: {str(e)}")
    
    return all_reviews

async def scrape_reviews(url: str, max_reviews: int = 500) -> Dict:
    """Main review scraping function."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()
        all_reviews = []
        successful_pages = 0
        
        try:
            # Initial page load
            logger.info(f"Loading page: {url}")
            await page.goto(url, wait_until='domcontentloaded')
            await page.wait_for_timeout(2000)

            page_num = 1
            while len(all_reviews) < max_reviews and page_num <= 50:
                logger.info(f"Scraping page {page_num}...")
                
                # Handle dynamic loading
                await handle_dynamic_loading(page)
                
                # Extract reviews using both methods
                new_reviews = await combine_extraction_methods(page)
                
                logger.info(f"Found {len(new_reviews)} reviews on page {page_num}")
                
                if new_reviews:
                    initial_review_count = len(all_reviews)
                    
                    existing_contents = set(r['body'] for r in all_reviews)
                    unique_reviews = [r for r in new_reviews if r['body'] not in existing_contents]
                    all_reviews.extend(unique_reviews)
                    
                    if len(all_reviews) > initial_review_count:
                        successful_pages += 1
                        logger.info(f"Found {len(unique_reviews)} new unique reviews on page {page_num}")
                    else:
                        logger.info("No new unique reviews found. Stopping the scraping process.")
                        break
                else:
                    logger.info("No reviews found on current page. Stopping the scraping process.")
                    break
                
                # Handle pagination
                if len(all_reviews) < max_reviews:
                    logger.info(f"Attempting to navigate to page {page_num + 1}")
                    has_next = await handle_pagination(context, page, page_num)
                    if not has_next:
                        logger.warning("No more pages available")
                        break
                    page_num += 1
                else:
                    break
            
            # Ensure reviews are not empty
            logger.info(f"Total reviews scraped: {len(all_reviews)}")
            
            # Create final result
            final_result = {
                "reviews": all_reviews,
                "reviews_count": len(all_reviews),
                "pages_with_unique_reviews": successful_pages,
                "url": url,
                "scrape_date": time.strftime("%Y-%m-%d %H:%M:%S")
            }
            
            return final_result
            
        except Exception as e:
            logger.error(f"Error during scraping: {str(e)}")
            return {
                "reviews": [],
                "reviews_count": 0,
                "pages_with_unique_reviews": 0,
                "url": url,
                "scrape_date": time.strftime("%Y-%m-%d %H:%M:%S")
            }
        finally:
            await context.close()
            await browser.close()
async def validate_reviews_with_llm(reviews: List[Dict]) -> List[Dict]:
    """
    Use Ollama to validate and enhance review data.
    """
    if not reviews:
        return reviews
        
    try:
        # Sample a few reviews for validation if there are many
        sample_size = min(5, len(reviews))
        sample_reviews = reviews[:sample_size]
        
        validation_prompt = f"""
        Analyze these reviews and identify if they are genuine product reviews:
        
        {json.dumps(sample_reviews, indent=2)}
        
        For each review, return only TRUE if it appears to be a genuine product review, 
        or FALSE if it seems to be navigation text, website content, or other non-review content.
        Return in format:
        1: TRUE/FALSE
        2: TRUE/FALSE
        etc.
        """
        
        result = await query_ollama(validation_prompt)
        
        # Parse validation results
        validation_results = []
        for line in result.split('\n'):
            if ':' in line:
                is_valid = 'TRUE' in line.split(':')[1].upper()
                validation_results.append(is_valid)
                
        # If majority of sampled reviews are invalid, apply stricter filtering
        if validation_results and sum(validation_results) / len(validation_results) < 0.5:
            logger.warning("Low validation score, applying stricter filtering")
            return [r for r in reviews if len(r['body'].split()) >= 5 and 
                   not any(word in r['body'].lower() for word in ['menu', 'navigation', 'search', 'cart'])]
                   
        return reviews
        
    except Exception as e:
        logger.error(f"Error in LLM validation: {str(e)}")
        return reviews

@app.get("/api/reviews", response_model=ReviewResponse)
async def get_reviews(
    page: str = Query(..., description="URL encoded page URL to scrape reviews from"),
    max_reviews: int = Query(500, ge=10, le=1000, description="Maximum number of reviews to scrape")
):
    """
    Scrape reviews from a given URL.
    
    Parameters:
    - page: URL encoded page URL to scrape reviews from
    - max_reviews: Maximum number of reviews to scrape (default: 500, min: 10, max: 1000)
    
    Returns:
    - JSON object containing reviews and metadata
    """
    try:
        decoded_url = unquote(page)
        result = await scrape_reviews(decoded_url, max_reviews)
        return ReviewResponse(**result)
    except Exception as e:
        logger.error(f"Error scraping reviews: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error scraping reviews: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)