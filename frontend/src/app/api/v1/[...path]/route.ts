import type { NextRequest } from "next/server";

import { proxyV1Request } from "@/lib/proxy";

export const dynamic = "force-dynamic";

interface V1RouteContext {
  params: Promise<{ path?: string[] }>;
}

export async function GET(request: NextRequest, context: V1RouteContext) {
  return proxyV1Request(request, context);
}

export async function POST(request: NextRequest, context: V1RouteContext) {
  return proxyV1Request(request, context);
}

export async function PUT(request: NextRequest, context: V1RouteContext) {
  return proxyV1Request(request, context);
}

export async function PATCH(request: NextRequest, context: V1RouteContext) {
  return proxyV1Request(request, context);
}

export async function DELETE(request: NextRequest, context: V1RouteContext) {
  return proxyV1Request(request, context);
}

export async function HEAD(request: NextRequest, context: V1RouteContext) {
  return proxyV1Request(request, context);
}
