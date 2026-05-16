"use client";

import { Button } from "../components/ui/button";
import { Card, CardContent } from "../components/ui/card";

export default function Error({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="mx-auto max-w-screen-xl px-4 py-6 sm:px-6">
      <Card className="border-red-200 bg-red-50 text-red-900">
        <CardContent>
        <h1 className="text-base font-semibold">Dashboard unavailable</h1>
        <p className="mt-2 text-sm">
          The dashboard could not finish loading. Check API readiness, then retry.
        </p>
        <Button className="mt-4 border-red-300" onClick={reset} variant="secondary">
          Retry
        </Button>
        </CardContent>
      </Card>
    </main>
  );
}
