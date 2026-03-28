import Link from "next/link";

export default function Home() {
  return (
    <main className="min-h-screen flex flex-col items-center bg-gray-50">
      {/* Hero */}
      <section className="flex flex-col items-center justify-center gap-6 px-8 pt-24 pb-16 text-center max-w-2xl">
        <h1 className="text-5xl font-bold text-gray-900 tracking-tight">auto-tessell</h1>
        <p className="text-xl text-gray-500 max-w-lg">
          Upload an STL file. Get a CFD or FEA-ready OpenFOAM polyMesh back in minutes.
          No setup, no licenses — just a ZIP you can drop straight into your solver.
        </p>

        <div className="flex gap-3 mt-2">
          <Link
            href="/mesh/new"
            className="px-7 py-3 bg-blue-600 text-white rounded-lg font-semibold text-base hover:bg-blue-700 transition-colors"
          >
            Generate Mesh
          </Link>
          <Link
            href="/jobs"
            className="px-7 py-3 bg-white border border-gray-300 text-gray-700 rounded-lg font-semibold text-base hover:border-gray-400 transition-colors"
          >
            Recent Jobs
          </Link>
        </div>
      </section>

      {/* How it works */}
      <section className="w-full max-w-3xl px-8 pb-16 grid grid-cols-3 gap-6 text-center">
        {[
          {
            step: "1",
            title: "Upload",
            body: "Binary or ASCII STL up to 100 MB. Drag-and-drop or file picker.",
          },
          {
            step: "2",
            title: "Mesh",
            body: "5-tier pipeline: geogram → Netgen → snappyHexMesh → pytetwild+MMG. First success wins.",
          },
          {
            step: "3",
            title: "Download",
            body: "checkMesh-validated polyMesh ZIP. Load into OpenFOAM, Salome, or any FEA solver.",
          },
        ].map(({ step, title, body }) => (
          <div key={step} className="bg-white border rounded-xl p-6 flex flex-col gap-2">
            <div className="w-8 h-8 rounded-full bg-blue-100 text-blue-700 font-bold text-sm flex items-center justify-center self-center">
              {step}
            </div>
            <p className="font-semibold text-gray-800">{title}</p>
            <p className="text-sm text-gray-500">{body}</p>
          </div>
        ))}
      </section>

      {/* Pricing */}
      <section className="w-full max-w-sm px-8 pb-20">
        <div className="bg-white border-2 border-blue-200 rounded-2xl p-8 flex flex-col gap-4 text-center shadow-sm">
          <p className="text-sm font-medium text-blue-600 uppercase tracking-wide">Simple pricing</p>
          <div>
            <span className="text-5xl font-bold text-gray-900">$5</span>
            <span className="text-gray-500 ml-1">/ mesh</span>
          </div>
          <p className="text-sm text-gray-500">Pay per job. No subscription. Full refund if generation fails.</p>
          <ul className="text-sm text-gray-600 flex flex-col gap-1.5 text-left mt-1">
            {[
              "Up to 2 concurrent jobs",
              "Any cell count — coarse to ultra-fine",
              "CFD (hex) or FEA (tet) purpose",
              "Pro mode: per-engine parameter overrides",
              "checkMesh quality report included",
            ].map((item) => (
              <li key={item} className="flex items-start gap-2">
                <span className="text-blue-500 mt-0.5">✓</span>
                {item}
              </li>
            ))}
          </ul>
          <Link
            href="/mesh/new"
            className="mt-2 px-6 py-3 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700 transition-colors"
          >
            Start now →
          </Link>
        </div>
      </section>
    </main>
  );
}
