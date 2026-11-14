import React from 'react';
import { BoltIcon, DocIcon, HeadsetIcon, PackageIcon } from '../../../components/icons';

interface HeroBannerProps {
  onQuickPrompt: (prompt: string) => void;
}

const CHIPS = [
  { Icon: BoltIcon, label: 'Tra cứu đơn hàng', prompt: 'Tra cứu đơn hàng của tôi' },
  { Icon: PackageIcon, label: 'Đổi trả / Hoàn tiền', prompt: 'Mình muốn đổi trả / hoàn tiền' },
  { Icon: DocIcon, label: 'Hỏi về chính sách', prompt: 'Mình muốn hỏi về chính sách' },
  { Icon: HeadsetIcon, label: 'Hỗ trợ khác', prompt: 'Mình cần hỗ trợ khác' },
];

export const HeroBanner: React.FC<HeroBannerProps> = ({ onQuickPrompt }) => (
  <div className="hero">
    <div className="art" />
    <h1>
      Xin chào! <span style={{ fontSize: '28.8px' }}>👋</span>
    </h1>
    <p>
      Tôi là trợ lý AI của ShopSupport, sẵn sàng hỗ trợ bạn 24/7 về đơn hàng, chính sách, đổi trả và các vấn đề khác.
    </p>
    <div className="chips">
      {CHIPS.map(({ Icon, label, prompt }) => (
        <button key={label} type="button" className="chip" onClick={() => onQuickPrompt(prompt)}>
          <Icon />
          {label}
        </button>
      ))}
    </div>
  </div>
);
