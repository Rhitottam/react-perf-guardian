import React, { useState, useEffect } from 'react';
import { UserCard } from './UserCard';

interface User {
  id: string;
  name: string;
  avatar: string;
}

export function UserList({ users }: { users: User[] }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filter, setFilter] = useState('');

  // Issue: derived state that could be computed
  const [filteredUsers, setFilteredUsers] = useState<User[]>(users);

  // Issue: effect syncing derived state
  useEffect(() => {
    setFilteredUsers(users.filter(u => u.name.includes(filter)));
  }, [users, filter]);

  return (
    <div>
      <input
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      />
      {filteredUsers.map(user => (
        <UserCard
          key={user.id}
          user={user}
          isSelected={selectedId === user.id}
          // Issue: inline function breaks UserCard's memo
          onSelect={() => setSelectedId(user.id)}
          // Issue: inline object
          style={{ padding: 10 }}
        />
      ))}
    </div>
  );
}
