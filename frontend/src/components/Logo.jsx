import { useId } from "react";

// Original mark: a chat bubble holding two rising chevrons ("lift" + "chat").
export function LogoMark({ size = 40, className = "" }) {
  const id = useId().replace(/:/g, "");
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 40 40"
      role="img"
      aria-label="Lyftr Chat logo"
    >
      <defs>
        <linearGradient id={`bg${id}`} x1="4" y1="2" x2="36" y2="38" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#6a6cff" />
          <stop offset="0.55" stopColor="#7c4dff" />
          <stop offset="1" stopColor="#b14dff" />
        </linearGradient>
        <linearGradient id={`ch${id}`} x1="14" y1="14" x2="26" y2="24" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#5b5bf0" />
          <stop offset="1" stopColor="#8a4dff" />
        </linearGradient>
        <radialGradient id={`hi${id}`} cx="0.25" cy="0.1" r="0.8">
          <stop offset="0" stopColor="#ffffff" stopOpacity="0.38" />
          <stop offset="1" stopColor="#ffffff" stopOpacity="0" />
        </radialGradient>
      </defs>
      <rect width="40" height="40" rx="11" fill={`url(#bg${id})`} />
      <rect width="40" height="40" rx="11" fill={`url(#hi${id})`} />
      <path
        d="M12 9.5h16a3.5 3.5 0 0 1 3.5 3.5v10a3.5 3.5 0 0 1-3.5 3.5h-7.4l-5.1 4.6a.6.6 0 0 1-1-.45V26.5H12a3.5 3.5 0 0 1-3.5-3.5V13A3.5 3.5 0 0 1 12 9.5Z"
        fill="#fff"
      />
      <path d="M14.6 19.6 20 14.2l5.4 5.4" fill="none" stroke={`url(#ch${id})`} strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M14.6 23.6 20 18.2l5.4 5.4" fill="none" stroke={`url(#ch${id})`} strokeOpacity="0.4" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Wordmark() {
  return (
    <h1 className="wordmark">
      <span className="wm-lyftr">Lyftr</span>
      <span className="wm-chat">Chat</span>
    </h1>
  );
}
