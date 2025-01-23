'use client';

import { useState } from 'react';
import axios from 'axios';
import { ReviewResponse } from './lib/types';
import URLInput from './components/URLInput';
import ReviewList from './components/ReviewList';
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/alert';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

export default function Home() {
  const [data, setData] = useState<ReviewResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (url: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const encodedUrl = encodeURIComponent(url);
      const response = await axios.get<ReviewResponse>(
        `${BACKEND_URL}/api/reviews?page=${encodedUrl}`
      );
      setData(response.data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred while scraping reviews');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <main className="min-h-screen bg-gray-50 py-8">
      <div className="container mx-auto px-4 space-y-8">
        <h1 className="text-3xl font-bold text-center mb-8">Review Scraper</h1>
        <URLInput onSubmit={handleSubmit} isLoading={isLoading} />
        
        {error && (
          <Alert variant="destructive" className="mt-4">
            <AlertTitle>Error</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        
        {data && <ReviewList data={data} />}
      </div>
    </main>
  );
}