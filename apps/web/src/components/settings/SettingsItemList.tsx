import type { ReactNode } from "react";

interface SettingsItemListProps<T> {
  emptyLabel: string;
  getKey: (item: T, index: number) => string;
  items: T[];
  onSelect: (index: number) => void;
  renderDescription?: (item: T, index: number) => ReactNode;
  renderTitle: (item: T, index: number) => ReactNode;
  renderTrailing?: (item: T, index: number) => ReactNode;
  selectedIndex: number;
}

export function SettingsItemList<T>({
  emptyLabel,
  getKey,
  items,
  onSelect,
  renderDescription,
  renderTitle,
  renderTrailing,
  selectedIndex,
}: SettingsItemListProps<T>) {
  return (
    <ul className="settings-item-list">
      {items.length > 0 ? (
        items.map((item, index) => (
          <li key={getKey(item, index)}>
            <button
              className={`settings-item${index === selectedIndex ? " settings-item--active" : ""}`}
              onClick={() => {
                onSelect(index);
              }}
              type="button"
            >
              <span className="settings-item__content">
                <strong>{renderTitle(item, index)}</strong>
                {renderDescription ? <small>{renderDescription(item, index)}</small> : null}
              </span>
              {renderTrailing ? <span className="settings-item__meta">{renderTrailing(item, index)}</span> : null}
            </button>
          </li>
        ))
      ) : (
        <li className="settings-empty-list">{emptyLabel}</li>
      )}
    </ul>
  );
}
