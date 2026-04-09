import { formatNumber } from "@/lib/format";

interface ChatHeaderProps {
  title: string;
  totalTokens: number;
}

export function ChatHeader({
  totalTokens,
  title,
}: ChatHeaderProps) {
  return (
    <header className="chat-header">
      <div className="chat-header__title-row">
        <h1 className="chat-header__title">{title}</h1>
        <span className="chat-header__token">
          {formatNumber(totalTokens)} token
        </span>
      </div>
    </header>
  );
}
