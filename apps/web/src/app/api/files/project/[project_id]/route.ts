import { NextRequest, NextResponse } from "next/server";

const AGENT_API_URL = process.env.AGENT_API_URL || "http://127.0.0.1:8000";

export async function DELETE(
  req: NextRequest,
  { params }: { params: Promise<{ project_id: string }> }
) {
  try {
    const { project_id: projectId } = await params;
    const { searchParams } = new URL(req.url);
    const targetUrl = new URL(
      `${AGENT_API_URL}/files/project/${encodeURIComponent(projectId)}`
    );

    const projectName = searchParams.get("projectName");
    if (projectName) {
      targetUrl.searchParams.set("project_name", projectName);
    }

    const response = await fetch(targetUrl.toString(), { method: "DELETE" });
    const text = await response.text();

    if (!response.ok) {
      return NextResponse.json(
        { error: text || "Backend project file deletion failed" },
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
    console.error("Project file delete API error:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
