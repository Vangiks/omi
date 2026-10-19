import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/firebase/admin';
import { verifyAdmin } from '@/lib/auth';
import { isSafeDocumentId } from '@/lib/firestore-doc-id.mjs';
export const dynamic = 'force-dynamic';


export async function PATCH(request: NextRequest, props: { params: Promise<{ id: string }> }) {
  const params = await props.params;
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const db = getDb();
    const body = await request.json();
    const { is_active, max_seats, organisation_name, website, employees } = body;
    const organizationId = params.id;
    if (!isSafeDocumentId(organizationId)) {
      return NextResponse.json({ error: 'Invalid id' }, { status: 400 });
    }

    // Exclude employees from updates - employees should not be editable through this endpoint
    if (employees !== undefined) {
      return NextResponse.json(
        { error: 'Employees cannot be updated through this endpoint' },
        { status: 400 }
      );
    }

    // Validate the fields being updated
    if (is_active !== undefined && typeof is_active !== 'boolean') {
      return NextResponse.json(
        { error: 'is_active must be a boolean value' },
        { status: 400 }
      );
    }

    if (max_seats !== undefined && (typeof max_seats !== 'number' || max_seats < 0)) {
      return NextResponse.json(
        { error: 'max_seats must be a non-negative number' },
        { status: 400 }
      );
    }

    if (organisation_name !== undefined && (typeof organisation_name !== 'string' || organisation_name.trim().length === 0)) {
      return NextResponse.json(
        { error: 'organisation_name must be a non-empty string' },
        { status: 400 }
      );
    }

    if (website !== undefined && typeof website !== 'string') {
      return NextResponse.json(
        { error: 'website must be a string' },
        { status: 400 }
      );
    }

    const orgRef = db.collection('organisations').doc(organizationId);
    const orgDoc = await orgRef.get();

    if (!orgDoc.exists) {
      return NextResponse.json(
        { error: 'Organization not found' },
        { status: 404 }
      );
    }

    // Build update object with only the fields that are provided
    const updateData: any = {};
    if (is_active !== undefined) {
      updateData.is_active = is_active;
    }
    if (max_seats !== undefined) {
      updateData.max_seats = max_seats;
    }
    if (organisation_name !== undefined) {
      updateData.organisation_name = organisation_name.trim();
    }
    if (website !== undefined) {
      updateData.website = website.trim();
    }

    await orgRef.update(updateData);

    const updatedDoc = await orgRef.get();
    const updatedData = updatedDoc.data();

    return NextResponse.json({
      success: true,
      organization: {
        id: updatedDoc.id,
        ...updatedData,
        added_on: updatedData?.added_on?.toDate?.()?.toISOString() || null,
        max_seats: updatedData?.max_seats || null,
        employees: updatedData?.employees?.map((emp: any) => ({
          ...emp,
          added_at: emp.added_at?.toDate?.()?.toISOString() || null,
          removed_at: emp.removed_at?.toDate?.()?.toISOString() || null,
        })) || []
      }
    });

  } catch (error) {
    console.error('Error updating organization:', error);
    return NextResponse.json(
      { error: 'Failed to update organization' },
      { status: 500 }
    );
  }
}
