'use client'
import { useState, useEffect } from 'react';
import { Star } from 'lucide-react';
import { Card, CardHeader, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Alert, AlertDescription } from '@/components/ui/alert';

interface Review {
  title?: string;
  body: string;
  rating: number;
  reviewer: string;
  date?: string;
}

interface ReviewsResponse {
  reviews: Review[];
  reviews_count: number;
  pages_with_unique_reviews: number;
  url: string;
  scrape_date: string;
}

function isValidUrl(url: string) {
  try {
    new URL(url);
    return true;
  } catch {
    return false;
  }
}
export default function Home() {
  const [url, setUrl] = useState('');
  const [reviews, setReviews] = useState<Review[]>([]);
  const [reviewsCount, setReviewsCount] = useState(0);
  const [pagesWithUniqueReviews, setPagesWithUniqueReviews] = useState(0);
  const [scrapeDate, setScrapeDate] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchReviews = async (page: number) => {
    setLoading(true);
    setError(null);
  
    if (!isValidUrl(url)) {
      setError('Please enter a valid URL');
      setLoading(false);
      return;
    }
  
    try {
      const encodedUrl = encodeURIComponent(url);
      const apiUrl = `/api/reviews?url=${encodedUrl}&page=${page}`;
      
      // Log the API URL being called
      console.log('Calling API URL:', apiUrl);
  
      const response = await fetch(apiUrl, {
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
        },
        method: 'GET',
      });
  
      // Log the raw response
      console.log('Raw Response:', response);
  
      if (!response.ok) {
        let errorMessage = 'Failed to fetch reviews';
        try {
          const errorData = await response.json();
          errorMessage = errorData.detail || errorMessage;
        } catch {
          errorMessage += `: ${response.statusText}`;
        }
        throw new Error(errorMessage);
      }
  
      const data: ReviewsResponse = await response.json();
      
      // Log the parsed data
      console.log('Parsed Data:', data);
  
      // Detailed logging of reviews
      console.log('Reviews Length:', data.reviews?.length);
      console.log('Reviews:', data.reviews);
  
      if (data.reviews && data.reviews.length > 0) {
        setReviews(data.reviews);
        setReviewsCount(data.reviews_count);
        setPagesWithUniqueReviews(data.pages_with_unique_reviews);
        setScrapeDate(data.scrape_date);
      } else {
        setError('No reviews found. Please try a different URL');
        setReviews([]);
        setReviewsCount(0);
        setPagesWithUniqueReviews(0);
        setScrapeDate('');
      }
    } catch (err) {
      console.error('Error details:', err);
      setError(err instanceof Error ? err.message : 'An error occurred while fetching reviews');
      setReviews([]);
    } finally {
      setLoading(false);
    }
  };
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url.trim()) {
      setError('Please enter a URL');
      return;
    }
    setReviews([]);
    setReviewsCount(0);
    setPagesWithUniqueReviews(0);
    setScrapeDate('');
    await fetchReviews(1);
  };

  const renderStars = (rating: number) => {
    return (
      <div className="flex">
        {[...Array(5)].map((_, i) => (
          <Star
            key={i}
            className={i < Math.round(rating) ? "fill-yellow-400 text-yellow-400" : "fill-gray-200 text-gray-200"}
            size={16}
          />
        ))}
      </div>
    );
  };

  return (
    <div className="max-w-4xl mx-auto p-4 space-y-4">
      <Card>
        <CardHeader>
          <h1 className="text-2xl font-bold">Reviews Extractor</h1>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="flex gap-2">
              <Input
                type="url"
                value={url}
                onChange={(e) => {
                  setUrl(e.target.value);
                  setError(null); // Clear error when input changes
                }}
                placeholder="Enter product URL (e.g., https://example.com/products/item)"
                className="flex-1"
                required
              />
              <Button 
                type="submit" 
                disabled={loading || !url.trim()}
                className="min-w-[120px]"
              >
                {loading ? 'Loading...' : 'Extract Reviews'}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      {error && (
        <Alert variant="destructive" className="animate-shake ">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {loading && reviews.length === 0 && (
        <Card>
          <CardContent className="p-8 text-center">
            <div className="animate-pulse">Loading reviews...</div>
          </ CardContent>
        </Card>
      )}

      {reviews.length > 0 && (
        <Card>
          <CardHeader>
            <h2 className="text-xl font-semibold">Extracted Reviews ({reviewsCount})</h2>
          </CardHeader>
          <CardContent>
            {reviews.map((review, index) => (
              <div key={index} className="border-b py-4">
                <h3 className="font-bold">{review.title || 'Untitled Review'}</h3>
                <p>{review.body}</p>
                {renderStars(review.rating)}
                <p className="text-sm text-gray-500">Reviewed by {review.reviewer} on {review.date}</p>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {reviews.length === 0 && !loading && (
        <Card>
          <CardContent className="p-8 text-center">
            <p>No reviews found. Please try a different URL.</p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}