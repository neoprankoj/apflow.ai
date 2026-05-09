"use client";

export default function Error({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="mx-auto max-w-7xl px-5 py-6">
      <div className="rounded-md border border-red-200 bg-red-50 p-5 text-red-900">
        <h1 className="text-base font-semibold">Dashboard unavailable</h1>
        <p className="mt-2 text-sm">
          The dashboard could not finish loading. Check API readiness, then retry.
        </p>
        <button className="mt-4 rounded-md border border-red-300 px-3 py-2 text-sm" onClick={reset} type="button">
          Retry
        </button>
      </div>
    </main>
  );
}
