import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface MarkdownMessageProps {
  className?: string;
  content: string;
}

export function MarkdownMessage({ className, content }: MarkdownMessageProps) {
  return (
    <div className={["markdown-message", className].filter(Boolean).join(" ")}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a({ node: _node, ...props }) {
            return <a {...props} rel="noreferrer" target="_blank" />;
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
