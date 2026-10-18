"""Shared Firestore read queries for serving endpoints."""

from database._client import get_firestore_client


def list_active_desktop_prompt_snapshots(*, firestore_client=None):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    return list(client.collection('desktop_prompts').where('active', '==', True).limit(50).stream())


def list_desktop_release_snapshots(*, firestore_client=None):
    client = firestore_client if firestore_client is not None else get_firestore_client()
    return list(client.collection('desktop_releases').order_by('build_number', direction='DESCENDING').stream())
