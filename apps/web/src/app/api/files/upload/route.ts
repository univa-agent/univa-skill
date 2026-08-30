import { NextRequest, NextResponse } from "next/server";

const AGENT_API_URL = process.env.AGENT_API_URL || "http://127.0.0.1:8000";

/**
 * POST /api/files/upload — Upload a file to the Python backend.
 *
 * Accepts multipart/form-data with a single file field "file".
 * Proxies to the Python backend's /files/upload endpoint.
 * Returns the server-side absolute path of the uploaded file.
 */
export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData();
    const file = formData.get("file");
    const projectId = formData.get("project_id");
    const projectName = formData.get("project_name");

    if (!file || !(file instanceof Blob)) {
      return NextResponse.json(
        { error: 'No file provided in "file" field' },
        { status: 400 }
      );
    }

    // Forward as multipart to Python backend
    const backendForm = new FormData();
    backendForm.append("file", file, (file as File).name || "upload");
    if (typeof projectId === "string") {
      backendForm.append("project_id", projectId);
    }
    if (typeof projectName === "string") {
      backendForm.append("project_name", projectName);
    }

    const targetUrl = `${AGENT_API_URL}/files/upload`;
    const response = await fetch(targetUrl, {
      method: "POST",
      body: backendForm,
      // Let undici/fetch handle multipart boundary automatically
    });

    if (!response.ok) {
      const text = await response.text();
      console.error("Upload backend error:", text);
      return NextResponse.json(
        { error: `Backend upload failed: ${text}` },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error("File upload API error:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
