import { NextRequest, NextResponse } from "next/server";

const AGENT_API_URL = process.env.AGENT_API_URL || "http://127.0.0.1:8000";

export async function DELETE(req: NextRequest) {
  try {
    const body = await req.json().catch(() => null);

    if (!body?.server_path || typeof body.server_path !== "string") {
      return NextResponse.json(
        { error: "server_path is required" },
        { status: 400 }
      );
    }

    const response = await fetch(`${AGENT_API_URL}/files/delete`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const text = await response.text();

    if (!response.ok) {
      return NextResponse.json(
        { error: text || "Backend file deletion failed" },
        { status: response.status }
      );
    }

    return new NextResponse(text, {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("Content-Type") || "application/json",
      },
    });
  } catch (error) {
    console.error("File delete API error:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
