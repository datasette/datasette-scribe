import { h } from "preact";
import { useEffect, useRef } from "preact/hooks";
import { Signal, useSignalEffect } from "@preact/signals";

const iframeApi = new Promise((resolve, reject) => {
  const tag = document.createElement("script");
  tag.src = "https://www.youtube.com/iframe_api";
  const firstScriptTag = document.getElementsByTagName("script")[0];
  firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);

  function onYouTubeIframeAPIReady() {
    resolve(window.YT);
  }
  // @ts-ignore
  window.onYouTubeIframeAPIReady = onYouTubeIframeAPIReady;
});

export function YoutubeVideo(props: {
  id: string;
  onStateChange: (event: any, currentTime: number) => void;
  seek: Signal<number>;
}) {
  const target = useRef<HTMLDivElement>(null);
  const player = useRef(null);

  useEffect(() => {
    if (!target.current) return;
    let p;
    const child = target.current.appendChild(document.createElement("div"));

    iframeApi.then((yt: any) => {
      p = new yt.Player(child, {
        videoId: props.id,
        events: {
          onReady: (e) => {},
          onStateChange: (e) => props.onStateChange(e, p.getCurrentTime()),
        },
      });
      player.current = p;
    });

    const id = setInterval(() => {
      if (!player.current || !player.current.getCurrentTime) return;
      const t = player.current.getCurrentTime();
      if (props.seek.value != t) {
        props.seek.value = t;
      }
    }, 250);

    return () => {
      if (p) p.destroy();
      clearInterval(id);
    };
  }, []);

  useSignalEffect(() => {
    // make sure seek.value is reference before early returns!
    props.seek.value;
    if (!player.current) return;
    if (Math.abs(props.seek.value - player.current.getCurrentTime()) > 2)
      player.current.seekTo(props.seek.value, true);
  });

  return <div ref={target}></div>;
}
export default iframeApi;
