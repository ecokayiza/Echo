import {
  ChatBubbleLeftRightIcon,
  CircleStackIcon,
  RectangleGroupIcon,
  WrenchScrewdriverIcon,
} from "@heroicons/react/24/outline";
import { useEffect, useState, type ReactNode } from "react";

type MobilePanel = "chat" | "sessions" | "database" | "tools";

interface WorkspacePanelControls {
  isMobile: boolean;
  openChat: () => void;
}

interface ResponsiveWorkspaceShellProps {
  activeSessionId?: string | null;
  chatOpenRequest?: number;
  chat: ReactNode;
  database: ReactNode;
  sessions: ReactNode | ((controls: WorkspacePanelControls) => ReactNode);
  tools: ReactNode;
}

const mobileTabs: Array<{
  id: MobilePanel;
  label: string;
  icon: typeof ChatBubbleLeftRightIcon;
}> = [
  { id: "chat", label: "Chat", icon: ChatBubbleLeftRightIcon },
  { id: "sessions", label: "Sessions", icon: RectangleGroupIcon },
  { id: "database", label: "Database", icon: CircleStackIcon },
  { id: "tools", label: "Tools", icon: WrenchScrewdriverIcon },
];

export function ResponsiveWorkspaceShell({
  activeSessionId,
  chatOpenRequest = 0,
  chat,
  database,
  sessions,
  tools,
}: ResponsiveWorkspaceShellProps) {
  const isMobile = useMediaQuery("(max-width: 767px)");
  const [activeMobilePanel, setActiveMobilePanel] = useState<MobilePanel>("chat");
  const [leftHidden, setLeftHidden] = useState(false);
  const [rightHidden, setRightHidden] = useState(false);
  const openChat = () => {
    setActiveMobilePanel("chat");
  };
  const resolvedSessions =
    typeof sessions === "function"
      ? sessions({
          isMobile,
          openChat,
        })
      : sessions;
  const mobileContent: Record<MobilePanel, ReactNode> = {
    chat,
    sessions: resolvedSessions,
    database,
    tools,
  };

  const desktopClassName = [
    "app-shell",
    leftHidden ? "app-shell--left-hidden" : "",
    rightHidden ? "app-shell--right-hidden" : "",
    leftHidden && rightHidden ? "app-shell--both-hidden" : "",
  ]
    .filter(Boolean)
    .join(" ");

  useEffect(() => {
    if (isMobile && activeSessionId) {
      setActiveMobilePanel("chat");
    }
  }, [activeSessionId, isMobile]);

  useEffect(() => {
    if (isMobile && chatOpenRequest > 0) {
      setActiveMobilePanel("chat");
    }
  }, [chatOpenRequest, isMobile]);

  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>

      <div className="app-frame">
        {isMobile ? (
          <div className="mobile-workspace">
            <main className="mobile-workspace__main" id="main-content">
              <div
                className={`mobile-workspace__panel mobile-workspace__panel--${activeMobilePanel}`}
                key={activeMobilePanel}
              >
                {mobileContent[activeMobilePanel]}
              </div>
            </main>

            <nav className="mobile-tabbar" aria-label="Workspace panels">
              {mobileTabs.map((tab) => {
                const Icon = tab.icon;
                const active = activeMobilePanel === tab.id;
                return (
                  <button
                    aria-current={active ? "page" : undefined}
                    aria-label={tab.label}
                    className={`mobile-tabbar__item${active ? " mobile-tabbar__item--active" : ""}`}
                    key={tab.id}
                    onClick={() => {
                      setActiveMobilePanel(tab.id);
                    }}
                    type="button"
                  >
                    <Icon />
                    <span>{tab.label}</span>
                  </button>
                );
              })}
            </nav>
          </div>
        ) : (
          <div className={desktopClassName}>
            <aside className="app-shell__sidebar" aria-label="Workspace sources">
              {resolvedSessions}
              {database}
            </aside>

            <main className="app-shell__main" id="main-content">
              <button
                aria-label={leftHidden ? "Show sessions panel" : "Hide sessions panel"}
                className="panel-toggle panel-toggle--left"
                onClick={() => {
                  setLeftHidden((current) => !current);
                }}
                type="button"
              >
                {leftHidden ? ">" : "<"}
              </button>

              <button
                aria-label={rightHidden ? "Show settings panel" : "Hide settings panel"}
                className="panel-toggle panel-toggle--right"
                onClick={() => {
                  setRightHidden((current) => !current);
                }}
                type="button"
              >
                {rightHidden ? "<" : ">"}
              </button>

              {chat}
            </main>

            <aside className="app-shell__rail" aria-label="Workspace tools">
              {tools}
            </aside>
          </div>
        )}
      </div>
    </>
  );
}

function useMediaQuery(query: string) {
  const [matches, setMatches] = useState(() => {
    if (typeof window === "undefined") {
      return false;
    }
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    const media = window.matchMedia(query);
    const onChange = () => {
      setMatches(media.matches);
    };
    onChange();
    media.addEventListener("change", onChange);
    return () => {
      media.removeEventListener("change", onChange);
    };
  }, [query]);

  return matches;
}
