import React, { memo } from 'react';

interface UserCardProps {
  user: { id: string; name: string; avatar: string };
  isSelected: boolean;
  onSelect: () => void;
  style?: React.CSSProperties;
}

// Memoized but receives unstable props
export const UserCard = memo(function UserCard({
  user,
  isSelected,
  onSelect,
  style
}: UserCardProps) {
  return (
    <div
      style={style}
      onClick={onSelect}
      className={isSelected ? 'selected' : ''}
    >
      <img src={user.avatar} alt={user.name} />
      <span>{user.name}</span>
    </div>
  );
});
