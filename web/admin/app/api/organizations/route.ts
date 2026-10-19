import { NextRequest, NextResponse } from 'next/server';
import admin, { getDb, getAdminAuth } from '@/lib/firebase/admin';
import { verifyAdmin } from '@/lib/auth';
export const dynamic = 'force-dynamic';


export async function GET(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const db = getDb();
    const organizationsRef = db.collection('organisations');
    const snapshot = await organizationsRef.orderBy('added_on', 'desc').get();
    
    const organizations = snapshot.docs.map(doc => ({
      id: doc.id,
      ...doc.data(),
      added_on: doc.data().added_on?.toDate?.()?.toISOString() || null,
      max_seats: doc.data().max_seats || null,
      employees: doc.data().employees?.map((emp: any) => ({
        ...emp,
        added_at: emp.added_at?.toDate?.()?.toISOString() || null,
        removed_at: emp.removed_at?.toDate?.()?.toISOString() || null,
      })) || []
    }));

    return NextResponse.json({ organizations });
  } catch (error) {
    console.error('Error fetching organizations:', error);
    return NextResponse.json(
      { error: 'Failed to fetch organizations' },
      { status: 500 }
    );
  }
}

export async function POST(request: NextRequest) {
  const authResult = await verifyAdmin(request);
  if (authResult instanceof NextResponse) return authResult;

  try {
    const db = getDb();
    const body = await request.json();
    const { organisation_name, website, admin_name, admin_email, max_seats } = body;

    if (!organisation_name || !admin_name || !admin_email) {
      return NextResponse.json(
        { error: 'Missing required fields: organisation_name, admin_name, admin_email' },
        { status: 400 }
      );
    }

    // Check if user exists in Firebase Auth (optional - they might not have signed up yet)
    let userRecord;
    let userUid = ''; // Empty string if user doesn't exist yet
    try {
      userRecord = await getAdminAuth().getUserByEmail(admin_email);
      userUid = userRecord.uid;

      // Check if user is already part of another organization
      const userDocRef = db.collection('users').doc(userRecord.uid);
      const userDoc = await userDocRef.get();

      if (userDoc.exists) {
        const userData = userDoc.data();
        if (userData?.organisation_id) {
          return NextResponse.json(
            { error: 'User is already a member of another organization. Please choose a different user.' },
            { status: 409 }
          );
        }
      }
    } catch (error: any) {
      if (error.code === 'auth/user-not-found') {
        // User doesn't exist yet - that's fine, invitation will be sent
        console.log(`User ${admin_email} not found, will send invitation for new user`);
        userUid = '';
      } else {
        throw error;
      }
    }

    const now = admin.firestore.Timestamp.now();

    // Create organization document
    const orgRef = db.collection('organisations').doc();
    const organisationData = {
      organisation_id: orgRef.id,
      organisation_name,
      website: website || '',
      added_on: now,
      max_seats: max_seats || null,
      employees: [{
        email: admin_email,
        is_active: false, // Not active until invitation is accepted
        role: 'admin',
        uid: userUid, // Empty string if user doesn't exist yet, populated if they do
        added_at: now,
        removed_at: null
      }]
    };

    // Create organization document
    // Note: We don't update the user's document here, even if the user exists.
    // The user must accept the invitation first, which will then update their user document
    // with the organisation_id. This is handled by the invitation acceptance flow.
    await orgRef.set(organisationData);

    return NextResponse.json({
      success: true,
      organization: {
        id: orgRef.id,
        ...organisationData,
        added_on: now.toDate().toISOString(),
        employees: organisationData.employees.map(emp => ({
          ...emp,
          added_at: emp.added_at.toDate().toISOString()
        }))
      }
    });

  } catch (error) {
    console.error('Error creating organization:', error);
    return NextResponse.json(
      { error: 'Failed to create organization' },
      { status: 500 }
    );
  }
}
