import Link from "next/link";

export default function Home() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center gap-8 p-8 bg-gray-50">
      <div className="text-center max-w-xl">
        <h1 className="text-4xl font-bold text-gray-900 mb-3">auto-tessell</h1>
        <p className="text-lg text-gray-600">
          Upload an STL file and get a CFD or FEA-ready OpenFOAM mesh in minutes.
        </p>
      </div>

      <div className="flex gap-4">
        <Link
          href="/mesh/new"
          className="px-6 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-colors"
        >
          Generate Mesh
        </Link>
        <Link
          href="/jobs"
          className="px-6 py-3 bg-white border border-gray-300 text-gray-700 rounded-lg font-medium hover:border-gray-400 transition-colors"
        >
          Recent Jobs
        </Link>
      </div>

      <div className="grid grid-cols-3 gap-6 mt-4 text-center text-sm text-gray-600 max-w-lg">
        <div>
          <div className="font-semibold text-gray-800 mb-1">Upload STL</div>
          <div>Any binary or ASCII STL up to 100 MB</div>
        </div>
        <div>
          <div className="font-semibold text-gray-800 mb-1">Auto-Mesh</div>
          <div>5-tier pipeline → OpenFOAM polyMesh</div>
        </div>
        <div>
          <div className="font-semibold text-gray-800 mb-1">Download</div>
          <div>polyMesh ZIP, checkMesh-validated in prod</div>
        </div>
      </div>
    </main>
  );
}
