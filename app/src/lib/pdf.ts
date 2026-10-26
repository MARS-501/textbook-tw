import { GlobalWorkerOptions, getDocument } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

GlobalWorkerOptions.workerSrc = workerUrl;

export interface PdfSummary {
  pageCount: number;
  landscape: boolean; // 第一頁是橫向：通常是投影片
}

export async function summarizePdf(data: Uint8Array): Promise<PdfSummary> {
  const doc = await getDocument({ data }).promise;
  try {
    const first = await doc.getPage(1);
    const { width, height } = first.getViewport({ scale: 1 });
    return { pageCount: doc.numPages, landscape: width > height };
  } finally {
    await doc.destroy();
  }
}
