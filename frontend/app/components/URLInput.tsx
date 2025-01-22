import { useState } from 'react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Search } from 'lucide-react';

interface URLInputProps {
  onSubmit: (url: string) => void;
  isLoading: boolean;
}

export default function URLInput({ onSubmit, isLoading }: URLInputProps) {
  const [url, setUrl] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (url.trim()) {
      onSubmit(url.trim());
    }
  };

  return (
    <form onSubmit={handleSubmit} className="w-full max-w-3xl mx-auto space-y-4">
      <div className="flex gap-2">
        <Input
          type="url"
          placeholder="Enter product URL to scrape reviews..."
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          className="flex-1"
          required
        />
        <Button type="submit" disabled={isLoading}>
          {isLoading ? (
            <div className="flex items-center">
              <div className="animate-spin mr-2">⚡</div>
              Scraping...
            </div>
          ) : (
            <div className="flex items-center">
              <Search className="mr-2 h-4 w-4" />
              Scrape Reviews
            </div>
          )}
        </Button>
      </div>
    </form>
  );
}