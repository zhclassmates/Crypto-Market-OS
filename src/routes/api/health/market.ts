import { createFileRoute } from "@tanstack/react-router";
import { markUiFetched, readMarketHealth } from "@/lib/rh/market-health-server";

export const Route = createFileRoute("/api/health/market")({
  server: {
    handlers: {
      GET: async () => Response.json(readMarketHealth()),
      POST: async ({ request }) => {
        let report = false;
        try {
          const body = await request.json();
          report = body?.reportUi === true;
        } catch {
          report = false;
        }
        if (report) markUiFetched();
        return Response.json(readMarketHealth());
      },
    },
  },
});
