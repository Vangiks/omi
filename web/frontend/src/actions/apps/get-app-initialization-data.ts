'use server';
import envConfig from '@/src/constants/envConfig';

export interface Category {
  title: string;
  id: string;
}

export interface TriggerEvent {
  title: string;
  id: string;
}

export interface NotificationScope {
  title: string;
  id: string;
}

export interface AppCapability {
  title: string;
  id: string;
  triggers?: TriggerEvent[];
  scopes?: NotificationScope[];
  actions?: unknown[];
}

export interface AppInitializationData {
  categories: Category[];
  capabilities: AppCapability[];
}

export default async function getAppInitializationData(): Promise<AppInitializationData> {
  const apiUrl = envConfig.API_URL || 'http://localhost:8000';

  try {
    // Fetch categories and capabilities in parallel (no auth required)
    const [categoriesResponse, capabilitiesResponse] = await Promise.all([
      fetch(`${apiUrl}/v1/app-categories`, {
        headers: {
          'Content-Type': 'application/json',
        },
        cache: 'no-cache',
      }),
      fetch(`${apiUrl}/v1/app-capabilities`, {
        headers: {
          'Content-Type': 'application/json',
        },
        cache: 'no-cache',
      }),
    ]);

    // Parse categories and capabilities
    const categories: Category[] = categoriesResponse.ok
      ? await categoriesResponse.json()
      : [];
    const capabilities: AppCapability[] = capabilitiesResponse.ok
      ? await capabilitiesResponse.json()
      : [];

    return {
      categories,
      capabilities,
    };
  } catch (error) {
    console.error('Error fetching app initialization data:', error);
    return {
      categories: [],
      capabilities: [],
    };
  }
}
