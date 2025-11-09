// src/hooks/useAuth.tsx
import {
  createContext,
  useContext,
  useEffect,
  useState,
  ReactNode,
} from 'react';
import {
  User,
  onAuthStateChanged,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signOut,
} from 'firebase/auth';
import { auth } from '@/lib/firebase';

interface AuthContextType {
  user: User | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  hasVoiceProfile: boolean;
  setHasVoiceProfile: (value: boolean) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [hasVoiceProfile, setHasVoiceProfile] = useState(false);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (fbUser) => {
      (async () => {
        setLoading(true);
        try {
          if (fbUser) {
            // we have an authenticated Firebase user
            setUser(fbUser);

            // 🔥 ask backend for that user's profile (instead of Firestore from browser)
            const params = new URLSearchParams({
              user_id: fbUser.uid,
            });
            // optionally pass email so backend can store it on first create
            if (fbUser.email) {
              params.append('email', fbUser.email);
            }

            const res = await fetch(
              `http://localhost:8000/user-profile?${params.toString()}`
            );

            if (!res.ok) {
              console.error('backend /user-profile failed with', res.status);
              // fallback to false so UI can still render
              setHasVoiceProfile(false);
            } else {
              const data = await res.json();
              // backend returns { hasVoiceProfile: bool, ... }
              setHasVoiceProfile(!!data.hasVoiceProfile);
            }
          } else {
            // logged out
            setUser(null);
            setHasVoiceProfile(false);
          }
        } catch (err) {
          console.error('Error loading user profile via backend:', err);
          setHasVoiceProfile(false);
        } finally {
          setLoading(false);
        }
      })();
    });

    return unsubscribe;
  }, []);

  // -------- SIGN IN --------
  const signIn = async (email: string, password: string) => {
    try {
      await signInWithEmailAndPassword(auth, email, password);
      // onAuthStateChanged will fire after this and fetch backend profile
    } catch (error: any) {
      let message = 'Something went wrong while signing in';
      if (error.code === 'auth/invalid-email') message = 'Invalid email format';
      else if (error.code === 'auth/user-not-found')
        message = 'No account found with this email';
      else if (error.code === 'auth/invalid-credential')
        message = 'Incorrect password, please try again';
      else if (error.code === 'auth/too-many-requests')
        message = 'Too many attempts. Try again later.';
      throw new Error(message);
    }
  };

  // -------- SIGN UP --------
  const signUp = async (email: string, password: string) => {
    try {
      const result = await createUserWithEmailAndPassword(auth, email, password);
      // we don't create Firestore from the frontend anymore;
      // after signup, onAuthStateChanged will call backend /user-profile
      // which will create the doc if missing.
      console.log('signed up firebase user', result.user.uid);
    } catch (error: any) {
      let message = 'Something went wrong while creating the account';
      if (error.code === 'auth/email-already-in-use')
        message = 'This email is already registered';
      else if (error.code === 'auth/invalid-email') message = 'Invalid email format';
      else if (error.code === 'auth/weak-password')
        message = 'Password should be at least 6 characters';
      throw new Error(message);
    }
  };

  const logout = async () => {
    await signOut(auth);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        signIn,
        signUp,
        logout,
        hasVoiceProfile,
        setHasVoiceProfile,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within AuthProvider');
  return context;
};
