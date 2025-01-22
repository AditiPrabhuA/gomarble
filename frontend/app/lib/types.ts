// app/lib/types.ts
export interface Review {
      title: string;
      body: string;
      rating: number | null;
      reviewer: string;
    }
    
    export interface ReviewResponse {
      reviews_count: number;
      reviews: Review[];
      pages_with_unique_reviews: number;
      url: string;
      scrape_date: string;
    }