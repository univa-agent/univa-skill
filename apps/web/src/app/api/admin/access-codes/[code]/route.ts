import { NextRequest, NextResponse } from 'next/server';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://127.0.0.1:8000';

/**
 * GET /api/admin/access-codes/[code] - Get access code details (admin only)
 */
export async function GET(
  req: NextRequest,
  { params }: { params: { code: string } }
) {
  try {
    const adminCode = req.headers.get('X-Access-Code');

    if (!adminCode) {
      return NextResponse.json(
        { error: 'Admin access code is required' },
        { status: 401 }
      );
    }

    const targetUrl = `${AGENT_API_URL}/admin/access-codes/${params.code}`;
    
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
    console.error('Get access code API error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}

/**
 * PUT /api/admin/access-codes/[code] - Update access code (admin only)
 */
export async function PUT(
  req: NextRequest,
  { params }: { params: { code: string } }
) {
  try {
    const adminCode = req.headers.get('X-Access-Code');

    if (!adminCode) {
      return NextResponse.json(
        { error: 'Admin access code is required' },
        { status: 401 }
      );
    }

    const body = await req.json();
    const targetUrl = `${AGENT_API_URL}/admin/access-codes/${params.code}`;
    
    const response = await fetch(targetUrl, {
      method: 'PUT',
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
    console.error('Update access code API error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}

/**
 * DELETE /api/admin/access-codes/[code] - Delete access code (admin only)
 */
export async function DELETE(
  req: NextRequest,
  { params }: { params: { code: string } }
) {
  try {
    const adminCode = req.headers.get('X-Access-Code');

    if (!adminCode) {
      return NextResponse.json(
        { error: 'Admin access code is required' },
        { status: 401 }
      );
    }

    const targetUrl = `${AGENT_API_URL}/admin/access-codes/${params.code}`;
    
    const response = await fetch(targetUrl, {
      method: 'DELETE',
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
    console.error('Delete access code API error:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}