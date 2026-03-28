"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { loadStripe } from "@stripe/stripe-js";
import {
  Elements,
  PaymentElement,
  useStripe,
  useElements,
} from "@stripe/react-stripe-js";
import { uploadSTL } from "@/lib/api";

const stripePromise = loadStripe(
  process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY ?? ""
);

// Stable user ID stored in localStorage (replaced by real auth later)
function getUserId(): string {
  if (typeof window === "undefined") return "anon";
  const key = "tessell_user_id";
  let id = localStorage.getItem(key);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(key, id);
  }
  return id;
}

// ----- Upload step -----

interface UploadStepProps {
  onUploaded: (jobId: string, clientSecret: string) => void;
}

function UploadStep({ onUploaded }: UploadStepProps) {
  const [dragging, setDragging] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleFile = useCallback((f: File) => {
    if (!f.name.toLowerCase().endsWith(".stl")) {
      setError("Only .stl files are accepted.");
      return;
    }
    if (f.size > 100 * 1024 * 1024) {
      setError("File must be under 100 MB.");
      return;
    }
    setError(null);
    setFile(f);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const f = e.dataTransfer.files[0];
      if (f) handleFile(f);
    },
    [handleFile]
  );

  const handleSubmit = async () => {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const userId = getUserId();
      const res = await uploadSTL(file, userId);
      onUploaded(res.job_id, res.client_secret);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="flex flex-col gap-6 w-full max-w-md">
      <h2 className="text-xl font-semibold text-gray-800">Upload your STL</h2>

      <div
        className={`border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-colors ${
          dragging ? "border-blue-400 bg-blue-50" : "border-gray-300 hover:border-gray-400"
        }`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => document.getElementById("stl-input")?.click()}
      >
        {file ? (
          <p className="text-gray-700 font-medium">{file.name} ({(file.size / 1024 / 1024).toFixed(1)} MB)</p>
        ) : (
          <p className="text-gray-500">Drop an STL file here, or click to browse</p>
        )}
        <input
          id="stl-input"
          type="file"
          accept=".stl"
          className="hidden"
          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
        />
      </div>

      {error && <p className="text-red-500 text-sm">{error}</p>}

      <button
        disabled={!file || uploading}
        onClick={handleSubmit}
        className="w-full py-3 bg-blue-600 text-white rounded-lg font-medium disabled:opacity-40 hover:bg-blue-700 transition-colors"
      >
        {uploading ? "Uploading..." : "Upload & Continue to Payment"}
      </button>
    </div>
  );
}

// ----- Payment step -----

interface PaymentFormProps {
  jobId: string;
  onPaid: () => void;
}

function PaymentForm({ jobId, onPaid }: PaymentFormProps) {
  const stripe = useStripe();
  const elements = useElements();
  const [paying, setPaying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handlePay = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!stripe || !elements) return;
    setPaying(true);
    setError(null);

    const { error: stripeError } = await stripe.confirmPayment({
      elements,
      confirmParams: {
        return_url: `${window.location.origin}/mesh/${jobId}`,
      },
    });

    if (stripeError) {
      setError(stripeError.message ?? "Payment failed");
      setPaying(false);
    } else {
      onPaid();
    }
  };

  return (
    <form onSubmit={handlePay} className="flex flex-col gap-6 w-full max-w-md">
      <h2 className="text-xl font-semibold text-gray-800">Payment — $5.00</h2>
      <PaymentElement />
      {error && <p className="text-red-500 text-sm">{error}</p>}
      <button
        type="submit"
        disabled={!stripe || paying}
        className="w-full py-3 bg-blue-600 text-white rounded-lg font-medium disabled:opacity-40 hover:bg-blue-700 transition-colors"
      >
        {paying ? "Processing..." : "Pay $5 and Generate Mesh"}
      </button>
    </form>
  );
}

// ----- Page -----

type Step = "upload" | "payment";

export default function NewMeshPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("upload");
  const [jobId, setJobId] = useState<string | null>(null);
  const [clientSecret, setClientSecret] = useState<string | null>(null);

  const handleUploaded = (jid: string, secret: string) => {
    setJobId(jid);
    setClientSecret(secret);
    setStep("payment");
  };

  const handlePaid = () => {
    if (jobId) router.push(`/mesh/${jobId}`);
  };

  return (
    <main className="min-h-screen flex flex-col items-center justify-center p-8 bg-gray-50">
      {step === "upload" && <UploadStep onUploaded={handleUploaded} />}

      {step === "payment" && clientSecret && (
        <Elements stripe={stripePromise} options={{ clientSecret }}>
          <PaymentForm jobId={jobId!} onPaid={handlePaid} />
        </Elements>
      )}
    </main>
  );
}
