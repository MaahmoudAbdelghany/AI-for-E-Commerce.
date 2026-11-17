import type { NextRequest } from "next/server";

import { proxyHealthRequest } from "@/lib/proxy";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  return proxyHealthRequest(request);
}

export async function POST(request: NextRequest) {
  return proxyHealthRequest(request);
}

export async function PUT(request: NextRequest) {
  return proxyHealthRequest(request);
}

export async function PATCH(request: NextRequest) {
  return proxyHealthRequest(request);
}

export async function DELETE(request: NextRequest) {
  return proxyHealthRequest(request);
}
