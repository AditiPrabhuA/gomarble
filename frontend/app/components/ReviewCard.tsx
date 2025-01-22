import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Star } from 'lucide-react';
import { Review } from '../lib/types';

interface ReviewCardProps {
  review: Review;
}

export default function ReviewCard({ review }: ReviewCardProps) {
  return (
    <Card className="w-full">
      <CardHeader className="pb-2">
        <div className="flex justify-between items-start">
          <CardTitle className="text-lg font-semibold">{review.title}</CardTitle>
          {review.rating && (
            <div className="flex items-center space-x-1">
              {[...Array(5)].map((_, i) => (
                <Star
                  key={i}
                  size={16}
                  className={i < review.rating! ? 'fill-yellow-400 text-yellow-400' : 'text-gray-300'}
                />
              ))}
            </div>
          )}
        </div>
        <p className="text-sm text-gray-500">By {review.reviewer}</p>
      </CardHeader>
      <CardContent>
        <p className="text-gray-700">{review.body}</p>
      </CardContent>
    </Card>
  );
}