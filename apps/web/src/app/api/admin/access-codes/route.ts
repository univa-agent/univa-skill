import { NextRequest, NextResponse } from 'next/server';

// Python agent server address
const AGENT_API_URL = process.env.AGENT_API_URL || 'http://127.0.0.1:8000';

/**
 * GET /api/admin/access-codes - List access codes (admin only)
 */
export async function GET(req: NextRequest) {
  try {
    const adminCode = req.headers.get('X-Access-Code');

    if (!adminCode) {
      return NextResponse.json(
        { error: 'Admin access code is required' },
        { status: 401 }
      );
    }

    // Forward query parameters
    const searchParams = req.nextUrl.searchParams;
    const queryString = searchParams.toString();
    const targetUrl = `${AGENT_API_URL}/admin/access-codes${queryString ? `?${queryString}` : ''}`;
    
    const response = await fetch(targetUrl, {
      method: 'GET',
      headers: {
        'X-Access-Code': adminCode,
      },
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
    console.error('Admin access codes API error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}

/**
 * POST /api/admin/access-codes - Create access code (admin only)
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
    const targetUrl = `${AGENT_API_URL}/admin/access-codes`;
    
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
    console.error('Create access code API error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}