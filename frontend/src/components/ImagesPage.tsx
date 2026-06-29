import { useState, useEffect, useCallback } from "react";

const API_BASE = "";

interface SizePreset {
  ratio: string;
  width: number;
  height: number;
  label: string;
}

interface SavedImage {
  filename: string;
  label: string;
  url: string;
  size: number;
}

interface ImagesPageProps {
  onPortToGraphics?: (imageUrl: string, sceneDescription: string) => void;
  onPortToLibrary?: (filename: string, label: string) => void;
}

export default function ImagesPage({ onPortToGraphics, onPortToLibrary }: ImagesPageProps) {
  const [sizes, setSizes] = useState<SizePreset[]>([]);
  const [sceneDescription, setSceneDescription] = useState("");
  const [aspectRatio, setAspectRatio] = useState("1:1");
  const [generating, setGenerating] = useState(false);
  const [generatedImage, setGeneratedImage] = useState<string | null>(null); // base64
  const [tempFilename, setTempFilename] = useState<string | null>(null);
  const [savedFilename, setSavedFilename] = useState<string | null>(null); // permanent filename after first save
  const [error, setError] = useState<string | null>(null);

  // Save modal state
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [saveLabel, setSaveLabel] = useState("");
  const [saveFilename, setSaveFilename] = useState("");
  const [portTo, setPortTo] = useState<"" | "library" | "graphics">("");
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);

  // Gallery
  const [savedImages, setSavedImages] = useState<SavedImage[]>([]);
  const [loadingGallery, setLoadingGallery] = useState(false);
  const [selectedGalleryImage, setSelectedGalleryImage] = useState<SavedImage | null>(null);
  const [confirmDeleteFilename, setConfirmDeleteFilename] = useState<string | null>(null);

  // Prompt Magic
  const [optimizing, setOptimizing] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/social-media-sizes`)
      .then((r) => r.json())
      .then(setSizes)
      .catch(() => {});
    loadGallery();
  }, []);

  const loadGallery = useCallback(() => {
    setLoadingGallery(true);
    fetch(`${API_BASE}/social-media-images`)
      .then((r) => r.json())
      .then((data) => { setSavedImages(data); setLoadingGallery(false); })
      .catch(() => setLoadingGallery(false));
  }, []);

  const handlePromptMagic = async () => {
    if (!sceneDescription.trim()) return;
    setOptimizing(true);
    try {
      const res = await fetch(`${API_BASE}/prompt-magic`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ description: sceneDescription }),
      });
      const data = await res.json();
      if (data.optimized_prompt) setSceneDescription(data.optimized_prompt);
    } catch {
      // silent fail
    } finally {
      setOptimizing(false);
    }
  };

  const handleGenerate = async () => {
    if (!sceneDescription.trim()) {
      setError("Please describe the scene first.");
      return;
    }
    setGenerating(true);
    setError(null);
    setGeneratedImage(null);
    setTempFilename(null);
    setSaveSuccess(null);
    try {
      const res = await fetch(`${API_BASE}/generate-social-image`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scene_description: sceneDescription, aspect_ratio: aspectRatio }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Generation failed");
      }
      const data = await res.json();
      setGeneratedImage(data.image_b64);
      setTempFilename(data.temp_filename);
      setSavedFilename(null); // reset saved filename on new generation
      // Auto-suggest a label from the scene description
      const autoLabel = sceneDescription.split(" ").slice(0, 5).join(" ");
      setSaveLabel(autoLabel);
      setSaveFilename(
        sceneDescription
          .toLowerCase()
          .replace(/[^a-z0-9\s]/g, "")
          .trim()
          .replace(/\s+/g, "_")
          .slice(0, 40)
      );
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Generation failed");
    } finally {
      setGenerating(false);
    }
  };

  const handleSave = async () => {
    if ((!tempFilename && !savedFilename) || !saveLabel.trim() || !saveFilename.trim()) return;
    setSaving(true);
    try {
      const res = await fetch(`${API_BASE}/save-social-image`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          temp_filename: tempFilename || savedFilename, // use saved filename if temp already consumed
          label: saveLabel,
          filename: saveFilename,
          port_to: portTo,
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Save failed");
      }
      const data = await res.json();
      setSaveSuccess(data.message);
      setSavedFilename(data.filename); // track permanent filename for subsequent saves
      setTempFilename(null); // temp is gone after first save
      setShowSaveModal(false);
      loadGallery();

      // Trigger cross-page porting
      if (portTo === "graphics" && onPortToGraphics && generatedImage) {
        onPortToGraphics(`data:image/png;base64,${generatedImage}`, sceneDescription);
      }
      if (portTo === "library" && onPortToLibrary) {
        onPortToLibrary(data.filename, saveLabel);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteGalleryImage = async (filename: string) => {
    try {
      const r = await fetch(`${API_BASE}/social-media-images/${encodeURIComponent(filename)}`, { method: 'DELETE' });
      if (r.ok) {
        setSavedImages(prev => prev.filter(img => img.filename !== filename));
        if (selectedGalleryImage?.filename === filename) {
          setSelectedGalleryImage(null);
        }
      }
    } catch {}
  };

  const selectedSize = sizes.find((s) => s.ratio === aspectRatio);

  return (
    <div className="max-w-5xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white">Unity Images</h1>
        <p className="text-gray-300 mt-1">
          Generate clean Unity images — no text, no logo — for organic social media posts.
          Save to the Social Media gallery, port to the Keyframe Library for videos, or send to Graphics for ad compositing.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Left: Generator */}
        <div className="space-y-6">
          <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
            <h2 className="text-base font-semibold text-gray-800 mb-4">Generate Image</h2>

            {/* Scene Description */}
            <div className="mb-4">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Unity Scene Description <span className="text-red-500">*</span>
              </label>
              <textarea
                className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-red-500 resize-none"
                rows={4}
                placeholder="e.g. Unity cleaning a window on the side of a house, sunny day, suburban neighborhood"
                value={sceneDescription}
                onChange={(e) => setSceneDescription(e.target.value)}
              />
              <button
                onClick={handlePromptMagic}
                disabled={optimizing || !sceneDescription.trim()}
                className="mt-2 flex items-center gap-1.5 text-xs text-purple-600 hover:text-purple-800 disabled:opacity-40 font-medium"
              >
                <span>{optimizing ? "✨ Optimizing..." : "✨ Prompt Magic — Optimize Scene"}</span>
              </button>
            </div>

            {/* Aspect Ratio */}
            <div className="mb-6">
              <label className="block text-sm font-medium text-gray-700 mb-2">Aspect Ratio</label>
              <div className="grid grid-cols-1 gap-2">
                {sizes.length === 0
                  ? ["1:1", "4:5", "9:16", "16:9", "4:3"].map((r) => (
                      <button
                        key={r}
                        onClick={() => setAspectRatio(r)}
                        className={`px-3 py-2 rounded-lg border text-sm text-left transition-colors ${
                          aspectRatio === r
                            ? "bg-red-600 text-white border-red-600"
                            : "bg-white text-gray-700 border-gray-300 hover:border-red-400"
                        }`}
                      >
                        <span className="font-semibold">{r}</span>
                      </button>
                    ))
                  : sizes.map((s) => (
                      <button
                        key={s.ratio}
                        onClick={() => setAspectRatio(s.ratio)}
                        className={`px-3 py-2 rounded-lg border text-sm text-left transition-colors ${
                          aspectRatio === s.ratio
                            ? "bg-red-600 text-white border-red-600"
                            : "bg-white text-gray-700 border-gray-300 hover:border-red-400"
                        }`}
                      >
                        <span className="font-semibold">{s.ratio}</span>
                        <span className={`ml-2 text-xs ${aspectRatio === s.ratio ? "text-red-100" : "text-gray-400"}`}>
                          {s.label}
                        </span>
                      </button>
                    ))}
              </div>
              {selectedSize && (
                <p className="mt-2 text-xs text-gray-400">
                  Output: {selectedSize.width} × {selectedSize.height}px
                </p>
              )}
            </div>

            {error && (
              <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
                {error}
              </div>
            )}

            {saveSuccess && (
              <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg text-sm text-green-700">
                ✅ {saveSuccess}
              </div>
            )}

            <button
              onClick={handleGenerate}
              disabled={generating || !sceneDescription.trim()}
              className="w-full bg-red-600 hover:bg-red-700 disabled:bg-gray-300 text-white font-semibold py-3 px-6 rounded-lg transition-colors"
            >
              {generating ? "Generating..." : "Generate Image"}
            </button>
          </div>
        </div>

        {/* Right: Preview */}
        <div className="space-y-4">
          {generating && (
            <div className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm flex flex-col items-center justify-center min-h-64">
              <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-red-600 mb-4" />
              <p className="text-sm text-gray-500">Generating Unity image...</p>
              <p className="text-xs text-gray-400 mt-1">This takes about 20–30 seconds</p>
            </div>
          )}

          {generatedImage && !generating && (
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
              <div className="p-4 border-b border-gray-100 flex items-center justify-between">
                <span className="text-sm font-semibold text-gray-800">Preview</span>
                <span className="text-xs text-gray-400 bg-gray-100 px-2 py-1 rounded">{aspectRatio}</span>
              </div>
              <div className="p-4">
                <img
                  src={`data:image/png;base64,${generatedImage}`}
                  alt="Generated Unity"
                  className="w-full rounded-lg object-contain max-h-96"
                />
              </div>

              {/* Action buttons */}
              <div className="p-4 border-t border-gray-100 space-y-2">
                <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Save & Use</p>

                {/* Save to Social Media */}
                <button
                  onClick={() => { setPortTo(""); setShowSaveModal(true); }}
                  className="w-full flex items-center gap-2 px-4 py-2.5 bg-gray-900 hover:bg-gray-800 text-white rounded-lg text-sm font-medium transition-colors"
                >
                  <span>💾</span>
                  <span>Save to Social Media Gallery</span>
                </button>

                {/* Port to Library */}
                <button
                  onClick={() => { setPortTo("library"); setShowSaveModal(true); }}
                  className="w-full flex items-center gap-2 px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors"
                >
                  <span>🎬</span>
                  <span>Save + Add to Video Keyframe Library</span>
                </button>

                {/* Port to Graphics */}
                <button
                  onClick={() => { setPortTo("graphics"); setShowSaveModal(true); }}
                  className="w-full flex items-center gap-2 px-4 py-2.5 bg-purple-600 hover:bg-purple-700 text-white rounded-lg text-sm font-medium transition-colors"
                >
                  <span>🎨</span>
                  <span>Save + Send to Graphics for Ad Compositing</span>
                </button>

                {/* Download directly */}
                <a
                  href={`data:image/png;base64,${generatedImage}`}
                  download={`unity_${aspectRatio.replace(":", "x")}_${Date.now()}.png`}
                  className="w-full flex items-center gap-2 px-4 py-2.5 border border-gray-300 hover:bg-gray-50 text-gray-700 rounded-lg text-sm font-medium transition-colors"
                >
                  <span>⬇️</span>
                  <span>Download PNG</span>
                </a>
              </div>
            </div>
          )}

          {!generatedImage && !generating && (
            <div className="bg-white rounded-xl border border-dashed border-gray-300 p-12 flex flex-col items-center justify-center text-center">
              <div className="text-4xl mb-3">🐕</div>
              <p className="text-sm text-gray-500">Your generated image will appear here</p>
              <p className="text-xs text-gray-400 mt-1">Describe a scene and click Generate</p>
            </div>
          )}
        </div>
      </div>

      {/* Save Modal */}
      {showSaveModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl w-full max-w-md p-6">
            <h3 className="text-lg font-bold text-gray-900 mb-1">Save Image</h3>
            <p className="text-sm text-gray-500 mb-4">
              {portTo === "library"
                ? "This image will be saved to the Social Media gallery AND added to the Video Keyframe Library."
                : portTo === "graphics"
                ? "This image will be saved to the Social Media gallery AND sent to the Graphics page for ad compositing."
                : "This image will be saved to the Social Media gallery."}
            </p>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Image Label</label>
                <input
                  type="text"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-red-500"
                  placeholder="e.g. Unity Cleaning Window"
                  value={saveLabel}
                  onChange={(e) => setSaveLabel(e.target.value)}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Filename (no spaces)</label>
                <input
                  type="text"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm text-gray-900 bg-white focus:outline-none focus:ring-2 focus:ring-red-500"
                  placeholder="e.g. unity_cleaning_window"
                  value={saveFilename}
                  onChange={(e) => setSaveFilename(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, "_"))}
                />
              </div>
            </div>

            <div className="flex gap-3 mt-6">
              <button
                onClick={() => setShowSaveModal(false)}
                className="flex-1 px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving || !saveLabel.trim() || !saveFilename.trim()}
                className="flex-1 px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-gray-300 text-white rounded-lg text-sm font-semibold"
              >
                {saving ? "Saving..." : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Gallery */}
      <div className="mt-12">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-bold text-white">Social Media Gallery</h2>
          <button
            onClick={loadGallery}
            className="text-sm text-gray-400 hover:text-gray-200"
          >
            Refresh
          </button>
        </div>

        {loadingGallery && (
          <p className="text-sm text-gray-300">Loading gallery...</p>
        )}

        {!loadingGallery && savedImages.length === 0 && (
          <div className="bg-gray-50 rounded-xl border border-dashed border-gray-300 p-10 text-center">
            <p className="text-sm text-gray-300">No images saved yet. Generate your first Unity image above.</p>
          </div>
        )}

        {savedImages.length > 0 && (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
            {savedImages.map((img) => (
              <div
                key={img.filename}
                className="group relative bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm hover:shadow-md transition-shadow cursor-pointer"
                onClick={() => setSelectedGalleryImage(img)}
              >
                <img
                  src={img.url}
                  alt={img.label}
                  className="w-full object-cover aspect-square"
                />
                {/* Trash icon overlay — visible on hover */}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setConfirmDeleteFilename(img.filename);
                  }}
                  className="absolute top-1.5 right-1.5 opacity-0 group-hover:opacity-100 transition-opacity bg-black/60 hover:bg-red-600 text-white rounded-full p-1"
                  title="Delete image"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clipRule="evenodd" />
                  </svg>
                </button>
                <div className="p-2">
                  <p className="text-xs font-medium text-gray-700 truncate">{img.label}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Delete Confirmation Dialog */}
      {confirmDeleteFilename && (
        <div
          className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4"
          onClick={() => setConfirmDeleteFilename(null)}
        >
          <div
            className="bg-white rounded-xl shadow-2xl max-w-sm w-full p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-lg font-semibold text-gray-900 mb-2">Delete Image?</h3>
            <p className="text-sm text-gray-500 mb-6">
              <span className="font-medium text-gray-700">{confirmDeleteFilename}</span> will be permanently removed from the gallery.
            </p>
            <div className="flex gap-3">
              <button
                onClick={() => setConfirmDeleteFilename(null)}
                className="flex-1 px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-700 hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  handleDeleteGalleryImage(confirmDeleteFilename);
                  setConfirmDeleteFilename(null);
                }}
                className="flex-1 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-sm font-semibold"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
      {/* Gallery Image Modal */}
      {selectedGalleryImage && (
        <div
          className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4"
          onClick={() => setSelectedGalleryImage(null)}
        >
          <div
            className="bg-white rounded-xl shadow-2xl max-w-lg w-full overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <img
              src={selectedGalleryImage.url}
              alt={selectedGalleryImage.label}
              className="w-full object-contain max-h-96"
            />
            <div className="p-4">
              <p className="font-semibold text-gray-900">{selectedGalleryImage.label}</p>
              <p className="text-xs text-gray-400 mt-0.5">{selectedGalleryImage.filename}</p>
              <div className="flex gap-2 mt-4">
                <a
                  href={selectedGalleryImage.url}
                  download={selectedGalleryImage.filename}
                  className="flex-1 text-center px-4 py-2 bg-gray-900 text-white rounded-lg text-sm font-medium hover:bg-gray-800"
                >
                  ⬇️ Download
                </a>
                <button
                  onClick={() => {
                    if (onPortToGraphics) {
                      onPortToGraphics(selectedGalleryImage.url, selectedGalleryImage.label);
                    }
                    setSelectedGalleryImage(null);
                  }}
                  className="flex-1 px-4 py-2 bg-purple-600 text-white rounded-lg text-sm font-medium hover:bg-purple-700"
                >
                  🎨 Send to Graphics
                </button>
                <button
                  onClick={() => {
                    setConfirmDeleteFilename(selectedGalleryImage.filename);
                    setSelectedGalleryImage(null);
                  }}
                  className="px-4 py-2 bg-red-50 border border-red-200 text-red-600 rounded-lg text-sm font-medium hover:bg-red-100"
                >
                  🗑️ Delete
                </button>
                <button
                  onClick={() => setSelectedGalleryImage(null)}
                  className="px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-700 hover:bg-gray-50"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
