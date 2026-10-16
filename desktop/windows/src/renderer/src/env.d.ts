/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Public share origin for conversation links (#4339). Default https://h.omi.me */
  readonly VITE_OMI_SHARE_BASE_URL?: string
  /** `host:port` of the Firebase Auth emulator; set only by the local-backend profile. */
  readonly VITE_FIREBASE_AUTH_EMULATOR_HOST?: string
}
