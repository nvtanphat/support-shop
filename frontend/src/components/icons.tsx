import React from 'react';

/** Icons of the ShopSupport design, with the original SVG paths (24x24 grid, 2.1 stroke from CSS). */
type IconProps = React.SVGProps<SVGSVGElement>;

const Svg: React.FC<IconProps & { children: React.ReactNode }> = ({ children, ...rest }) => (
  <svg viewBox="0 0 24 24" aria-hidden="true" {...rest}>
    {children}
  </svg>
);

export const ChatIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1.1-4.4A8 8 0 1 1 21 12z" />
    <path d="M9 11.5h.01M12 11.5h.01M15 11.5h.01" strokeWidth="2.6" />
  </Svg>
);
export const OrderLookupIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3 7l9-4 9 4-9 4-9-4z" />
    <path d="M3 7v10l9 4 9-4V7" />
    <circle cx="12" cy="13" r="2.5" />
  </Svg>
);
export const ReceiptIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M6 3h12v18l-3-2-3 2-3-2-3 2V3z" />
    <path d="M9.5 8h5M9.5 12h5" />
  </Svg>
);
export const RefreshIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M20 12a8 8 0 0 0-13.7-5.6L4 8.5M4 4v4.5h4.5M4 12a8 8 0 0 0 13.7 5.6l2.3-2.1M20 20v-4.5h-4.5" />
  </Svg>
);
export const SupportIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9.5" />
    <path d="M12 6.5a5.5 5.5 0 0 0-5.5 5.5v3a2 2 0 0 0 4 0v-2a2 2 0 0 0-2-2M17.5 12v3a2 2 0 0 1-4 0v-2a2 2 0 0 1 2-2M12 21.5v-1" />
  </Svg>
);
export const SearchIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="11" cy="11" r="7" />
    <path d="M20.5 20.5L16 16" />
  </Svg>
);
export const CartIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3 4h2.5l2.3 11h10.5l2.2-8H6.5" />
    <circle cx="9.5" cy="19.5" r="1.3" />
    <circle cx="17" cy="19.5" r="1.3" />
  </Svg>
);
export const UserIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="8" r="4" />
    <path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7" />
  </Svg>
);
export const BoltIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M13 2L4 14h7l-1 8 9-12h-7l1-8z" />
  </Svg>
);
export const PackageIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3 7l9-4 9 4v10l-9 4-9-4V7z" />
    <path d="M3 7l9 4 9-4M12 11v10" />
  </Svg>
);
export const DocIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M6 3h9l4 4v14H6z" />
    <path d="M14 3v5h5M9 13h7M9 17h7" />
  </Svg>
);
export const HeadsetIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M4 14v-2a8 8 0 0 1 16 0v2" />
    <rect x="3" y="14" width="4" height="6" rx="1.5" />
    <rect x="17" y="14" width="4" height="6" rx="1.5" />
    <path d="M19 20a4 3 0 0 1-4 2h-2" />
  </Svg>
);
export const CheckIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5 12.5l4.5 4.5L19 7.5" />
  </Svg>
);
export const InfoIcon = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9.5" />
    <path d="M12 11v5.5M12 7.5v.01" strokeWidth="2.2" />
  </Svg>
);
export const PlusIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 5v14M5 12h14" />
  </Svg>
);
export const MicIcon = (p: IconProps) => (
  <Svg {...p}>
    <rect x="9" y="3" width="6" height="12" rx="3" />
    <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
  </Svg>
);
export const SendIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M21 3L10 14M21 3l-7 18-4-7-7-4 18-7z" />
  </Svg>
);
export const OrderPanelIcon = (p: IconProps) => (
  <Svg {...p}>
    <rect x="3" y="3" width="18" height="18" rx="3" />
    <path d="M3 9h18M9 9v12M13 14h5M13 17h3" />
  </Svg>
);
export const CalendarIcon = (p: IconProps) => (
  <Svg {...p}>
    <rect x="3" y="5" width="18" height="16" rx="3" />
    <path d="M3 10h18M8 3v4M16 3v4" />
  </Svg>
);
export const TruckIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M2 6h12v10H2zM14 9h4l4 4v3h-8" />
    <circle cx="7" cy="18" r="2" />
    <circle cx="17" cy="18" r="2" />
  </Svg>
);
export const CardIcon = (p: IconProps) => (
  <Svg {...p}>
    <rect x="3" y="5" width="18" height="14" rx="3" />
    <path d="M3 10h18M7 15h4" />
  </Svg>
);
export const ChevronIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M9 5l7 7-7 7" />
  </Svg>
);

/** The two-tone book of the "related policies" panel; the gradient is part of the design. */
export const PolicyBookIcon = ({ className }: { className?: string }) => (
  <svg className={className} viewBox="0 0 24 24" aria-hidden="true" style={{ fill: 'url(#ss-book)', stroke: 'none' }}>
    <defs>
      <linearGradient id="ss-book" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stopColor="#a855f7" />
        <stop offset="1" stopColor="#6d28d9" />
      </linearGradient>
    </defs>
    <path d="M12 6.2C9.8 4.4 6.6 3.9 2.5 4.3v13.6c4.1-.4 7.3.1 9.5 1.9 2.2-1.8 5.4-2.3 9.5-1.9V4.3c-4.1-.4-7.3.1-9.5 1.9z" />
    <path
      d="M12 7v11.6M2.5 19.4c4-.5 7.2 0 9.5 1.6 2.3-1.6 5.5-2.1 9.5-1.6"
      fill="none"
      stroke="#fff"
      strokeOpacity=".55"
      strokeWidth="1"
      strokeLinecap="round"
    />
  </svg>
);
