import { useEffect, useRef, useState } from 'react';

/**
 * Frontend-only typewriter:
 * - reveals `text` character by character at ~speed cps
 * - if `text` changes mid-typing, jumps to the new text and starts over from the
 *   shared prefix length — so streaming-like overrides don't cause flicker
 * - returns { display, isTyping }
 */
export function useTypewriter(text: string, speed = 32) {
  const [display, setDisplay] = useState(text);
  const [isTyping, setIsTyping] = useState(false);
  const targetRef = useRef(text);
  const idxRef = useRef(text.length);
  const rafRef = useRef<number | null>(null);
  const lastTickRef = useRef<number>(0);

  useEffect(() => {
    if (text === targetRef.current) return;
    // shared prefix length
    let common = 0;
    const prev = targetRef.current;
    while (
      common < prev.length &&
      common < text.length &&
      prev.charCodeAt(common) === text.charCodeAt(common)
    ) common++;
    targetRef.current = text;
    // Either continue typing forward, or shrink to common prefix
    idxRef.current = Math.min(idxRef.current, common);
    setIsTyping(true);
    lastTickRef.current = performance.now();

    const step = (now: number) => {
      const elapsed = now - lastTickRef.current;
      const charsPerMs = speed / 1000;
      const advance = Math.max(1, Math.floor(elapsed * charsPerMs));
      idxRef.current = Math.min(targetRef.current.length, idxRef.current + advance);
      setDisplay(targetRef.current.slice(0, idxRef.current));
      lastTickRef.current = now;
      if (idxRef.current < targetRef.current.length) {
        rafRef.current = requestAnimationFrame(step);
      } else {
        setIsTyping(false);
        rafRef.current = null;
      }
    };
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(step);

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    };
  }, [text, speed]);

  return { display, isTyping };
}
