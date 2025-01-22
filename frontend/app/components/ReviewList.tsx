import { ReviewResponse } from '../lib/types';
import ReviewCard from './ReviewCard';

interface ReviewListProps {
  data: ReviewResponse;
}

export default function ReviewList({ data }: ReviewListProps) {
  return (
    <div className="w-full space-y-6">
      <div className="bg-white p-4 rounded-lg shadow">
        <h2 className="text-xl font-bold mb-2">Scrape Results</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
          <div>
            <p><span className="font-semibold">Total Reviews:</span> {data.reviews_count}</p>
            <p><span className="font-semibold">Pages Scraped:</span> {data.pages_with_unique_reviews}</p>
          </div>
          <div>
            <p><span className="font-semibold">Scrape Date:</span> {data.scrape_date}</p>
            <p>
              <span className="font-semibold">URL:</span>
              <a 
                href={data.url} 
                className="text-blue-600 hover:underline ml-1 block truncate" 
                target="_blank" 
                rel="noopener noreferrer"
              >
                {data.url}
              </a>
            </p>
          </div>
        </div>
      </div>
      
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {data.reviews.map((review, index) => (
          <ReviewCard key={index} review={review} />
        ))}
      </div>
    </div>
  );
}