import { initializeApp, getApps, getApp } from 'firebase/app';
import {
  initializeFirestore,
  persistentLocalCache,
  persistentMultipleTabManager,
  getFirestore,
  connectFirestoreEmulator
} from 'firebase/firestore';
import { getAuth, connectAuthEmulator } from 'firebase/auth';
import { connectStorageEmulator, getStorage } from 'firebase/storage';


const firebaseConfig = {
  apiKey: "AIzaSyCUa5R2rROL3Q--F570TQiiZD3zZv29oA8",
  authDomain: "ai-hackathon-4e25e.firebaseapp.com",
  projectId: "ai-hackathon-4e25e",
  storageBucket: "ai-hackathon-4e25e.firebasestorage.app",
  messagingSenderId: "842663746563",
  appId: "1:842663746563:web:03ca5edde7e1b10e6b0236",
  measurementId: "G-YQL8T7G2ZK",
};

// 1) app: initialize once
const app = !getApps().length ? initializeApp(firebaseConfig) : getApp();

// 2) firestore: try to get existing one first
let db;
try {
  // if we already initialized with options earlier in this HMR session
  db = getFirestore(app);
} catch {
  // first time: create with long polling
  const db = initializeFirestore(app, {
    experimentalForceLongPolling: true,   // use HTTP long-polling instead of websocket
    localCache: persistentLocalCache({
      tabManager: persistentMultipleTabManager(),
    }),
  });
}

export const auth = getAuth(app);
const storage = getStorage(app);

if  (location.hostname === 'localhost' || location.hostname === '127.0.0.1') {
  connectFirestoreEmulator(db, 'localhost',8080);
  connectStorageEmulator(storage,'localhost',9199);
}

export { app, storage, db };
