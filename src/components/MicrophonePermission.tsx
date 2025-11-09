import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Mic, CheckCircle2, AlertCircle } from "lucide-react";
import { useToast } from "@/hooks/use-toast";

type PermissionStatus = "prompt" | "granted" | "denied" | "checking";

interface MicrophonePermissionProps {
  onPermissionGranted?: () => void; // optional callback
}

const MicrophonePermission = ({ onPermissionGranted }: MicrophonePermissionProps) => {
  const [permissionStatus, setPermissionStatus] = useState<PermissionStatus>("prompt");
  const { toast } = useToast();

  const requestMicrophoneAccess = async () => {
    setPermissionStatus("checking");

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      // stop right away, we only needed the permission
      stream.getTracks().forEach((track) => track.stop());

      setPermissionStatus("granted");
      toast({
        title: "Microphone Access Granted",
        description: "You can now use voice features in this app.",
      });

      // tell parent so it can move to auth / calibration
      if (onPermissionGranted) onPermissionGranted();
    } catch (error) {
      console.error("Microphone access denied:", error);
      setPermissionStatus("denied");
      toast({
        title: "Microphone Access Denied",
        description: "Please enable microphone access in your browser settings.",
        variant: "destructive",
      });
    }
  };

  const renderContent = () => {
    switch (permissionStatus) {
      case "granted":
        return (
          <div className="text-center space-y-4 animate-fade-in">
            <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-primary/10 animate-pulse-glow">
              <CheckCircle2 className="w-10 h-10 text-primary" />
            </div>
            <h2 className="text-2xl font-bold text-foreground">All Set!</h2>
            <p className="text-muted-foreground max-w-md mx-auto">
              Microphone access has been granted. You can now use all voice features.
            </p>
          </div>
        );

      case "denied":
        return (
          <div className="text-center space-y-4 animate-fade-in">
            <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-destructive/10">
              <AlertCircle className="w-10 h-10 text-destructive" />
            </div>
            <h2 className="text-2xl font-bold text-foreground">Access Denied</h2>
            <p className="text-muted-foreground max-w-md mx-auto">
              Microphone access was denied. Please enable it in your browser settings and refresh the
              page.
            </p>
            <Button onClick={() => setPermissionStatus("prompt")} variant="outline">
              Try Again
            </Button>
          </div>
        );

      case "checking":
        return (
          <div className="text-center space-y-4">
            <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-primary/10 animate-pulse">
              <Mic className="w-10 h-10 text-primary" />
            </div>
            <h2 className="text-2xl font-bold text-foreground">Checking Access...</h2>
            <p className="text-muted-foreground max-w-md mx-auto">
              Please allow microphone access when prompted by your browser.
            </p>
          </div>
        );

      default:
        return (
          <div className="text-center space-y-4 animate-fade-in">
            <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-gradient-hero shadow-glow">
              <Mic className="w-10 h-10 text-white" />
            </div>
            <h2 className="text-2xl font-bold text-foreground">Microphone Access Required</h2>
            <p className="text-muted-foreground max-w-md mx-auto">
              This app needs access to your microphone to provide voice features. Your audio is
              processed securely and never stored without your permission.
            </p>
            <Button
              onClick={requestMicrophoneAccess}
              size="lg"
              className="bg-gradient-hero hover:opacity-90 transition-opacity shadow-glow"
            >
              <Mic className="w-5 h-5 mr-2" />
              Enable Microphone
            </Button>
          </div>
        );
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-subtle p-4">
      <Card className="max-w-2xl w-full p-8 shadow-card">{renderContent()}</Card>
    </div>
  );
};

export default MicrophonePermission;
