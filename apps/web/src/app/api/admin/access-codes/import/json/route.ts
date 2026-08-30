import { NextRequest, NextResponse } from 'next/server';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://127.0.0.1:8000';

/**
 * POST /api/admin/access-codes/import/json - Import access codes from JSON (admin only)
 */
export async function POST(req: NextRequest) {
  try {
    const adminCode = req.headers.get('X-Access-Code');

    if (!adminCode) {
      return NextResponse.json(
        { error: 'Admin access code is required' },
        { status: 401 }
      );
    }

    const body = await req.json();
    const targetUrl = `${AGENT_API_URL}/admin/access-codes/import/json`;
    
    const response = await fetch(targetUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Access-Code': adminCode,
      },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error('Agent API error:', errorText);
      return NextResponse.json(
        { error: `Agent API error: ${errorText}` },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
    
  } catch (error) {
    console.error('Import access codes API error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}