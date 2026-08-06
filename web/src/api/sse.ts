export interface SseFrame {
  event: string;
  data: string;
}

export function parseSseFrames(buffer: string): SseFrame[] {
  const frames: SseFrame[] = [];
  for (const block of buffer.split("\n\n")) {
    const trimmed = block.trim();
    if (!trimmed) continue;
    let event = "";
    let data = "";
    for (const line of trimmed.split("\n")) {
      if (line.startsWith("event:")) event = line.slice("event:".length).trim();
      else if (line.startsWith("data:")) data = line.slice("data:".length).trim();
    }
    frames.push({ event, data });
  }
  return frames;
}

export function takeFrames(buffer: string): { frames: SseFrame[]; rest: string } {
  const sep = buffer.lastIndexOf("\n\n");
  if (sep === -1) return { frames: [], rest: buffer };
  return {
    frames: parseSseFrames(buffer.slice(0, sep)),
    rest: buffer.slice(sep + 2),
  };
}
