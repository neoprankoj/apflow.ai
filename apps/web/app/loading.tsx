import { Card, CardContent } from "../components/ui/card";
import { LoadingSkeleton } from "../components/ui/loading-skeleton";

export default function Loading() {
  return (
    <main className="mx-auto max-w-screen-xl px-4 py-6 sm:px-6">
      <Card>
        <CardContent className="space-y-4">
          <LoadingSkeleton className="h-5 w-44" />
          <LoadingSkeleton className="h-24 w-full" />
          <LoadingSkeleton className="h-24 w-full" />
        </CardContent>
      </Card>
    </main>
  );
}
