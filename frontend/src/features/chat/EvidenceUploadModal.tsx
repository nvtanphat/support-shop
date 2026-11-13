import React, { useState, useRef } from 'react';
import { api } from '../../lib/api';
import { X, UploadCloud, FileCheck, AlertCircle, Loader2 } from 'lucide-react';
import { useEscapeKey } from '../../lib/useEscapeKey';

interface EvidenceUploadModalProps {
  returnCode: string | null;
  onClose: () => void;
  onSuccess: () => void;
}

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'video/mp4'];

export const EvidenceUploadModal: React.FC<EvidenceUploadModalProps> = ({
  returnCode,
  onClose,
  onSuccess,
}) => {
  useEscapeKey(onClose);
  const [files, setFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  if (!returnCode) return null;

  const handleFileChange = (newFiles: FileList | null) => {
    if (!newFiles) return;
    setError(null);
    const validFiles: File[] = [];
    const validPreviews: string[] = [];

    for (let i = 0; i < newFiles.length; i++) {
      const file = newFiles[i];
      if (!ALLOWED_TYPES.includes(file.type)) {
        setError(`Định dạng "${file.name}" không hợp lệ. Chỉ chấp nhận JPG, PNG, WEBP, MP4.`);
        return;
      }
      if (file.size > MAX_FILE_SIZE) {
        setError(`Tệp "${file.name}" vượt quá dung lượng tối đa 10MB.`);
        return;
      }
      validFiles.push(file);
      if (file.type.startsWith('image/')) {
        validPreviews.push(URL.createObjectURL(file));
      } else {
        validPreviews.push(''); // Video placeholder
      }
    }

    setFiles((prev) => [...prev, ...validFiles]);
    setPreviews((prev) => [...prev, ...validPreviews]);
  };

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
    setPreviews((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (files.length === 0) {
      setError('Vui lòng chọn ít nhất 1 hình ảnh hoặc video bằng chứng.');
      return;
    }

    setUploading(true);
    setError(null);
    try {
      await api.uploadEvidence(returnCode, files);
      onSuccess();
      onClose();
    } catch (err: any) {
      setError(err.message || 'Tải tệp lên thất bại.');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-3xl shadow-2xl max-w-md w-full p-6 text-slate-800 relative border border-purple-100 animate-in fade-in zoom-in-95"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
      >
        <button
          onClick={onClose}
          className="absolute top-5 right-5 text-slate-400 hover:text-slate-600 rounded-xl p-1 hover:bg-slate-100 transition"
        >
          <X className="w-5 h-5" />
        </button>

        <h3 className="text-base font-bold text-slate-900 mb-1">
          Cung cấp bằng chứng sản phẩm
        </h3>
        <p className="text-xs text-purple-700 mb-4 font-mono font-semibold">
          Yêu cầu trả hàng: {returnCode}
        </p>

        {error && (
          <div className="p-3 mb-4 bg-red-50 text-red-700 text-xs rounded-lg border border-red-200 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              handleFileChange(e.dataTransfer.files);
            }}
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition ${
              dragOver ? 'border-emerald-600 bg-emerald-50' : 'border-slate-300 hover:border-slate-400 bg-slate-50'
            }`}
          >
            <input
              type="file"
              ref={fileInputRef}
              multiple
              accept="image/jpeg,image/png,image/webp,video/mp4"
              className="hidden"
              onChange={(e) => handleFileChange(e.target.files)}
            />
            <UploadCloud className="w-8 h-8 text-slate-400 mx-auto mb-2" />
            <div className="text-sm font-medium text-slate-700">
              Kéo thả hoặc bấm để chọn ảnh/video
            </div>
            <div className="text-xs text-slate-500 mt-1">
              Tối đa 10MB/tệp (JPG, PNG, WEBP, MP4)
            </div>
          </div>

          {/* Previews */}
          {files.length > 0 && (
            <div className="grid grid-cols-3 gap-2 mt-4 max-h-36 overflow-y-auto p-1">
              {files.map((_, idx) => (
                <div key={idx} className="relative rounded-lg border border-slate-200 overflow-hidden group bg-slate-100">
                  {previews[idx] ? (
                    <img src={previews[idx]} alt="preview" className="w-full h-16 object-cover" />
                  ) : (
                    <div className="w-full h-16 flex items-center justify-center text-xs text-slate-500 font-mono">
                      VIDEO
                    </div>
                  )}
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      removeFile(idx);
                    }}
                    className="absolute top-1 right-1 bg-slate-900/70 text-white rounded-full p-0.5 hover:bg-slate-900"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </div>
              ))}
            </div>
          )}

          <div className="flex justify-end gap-3 mt-6">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 border border-slate-200 hover:bg-slate-50 rounded-xl text-xs font-semibold text-slate-700 transition"
            >
              Hủy
            </button>
            <button
              type="submit"
              disabled={uploading || files.length === 0}
              className="px-4 py-2 bg-purple-700 hover:bg-purple-700 text-white rounded-xl text-xs font-semibold flex items-center gap-2 disabled:opacity-50 shadow-md shadow-purple-200 transition"
            >
              {uploading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Đang tải lên...</span>
                </>
              ) : (
                <>
                  <FileCheck className="w-4 h-4" />
                  <span>Hoàn tất tải lên ({files.length})</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
