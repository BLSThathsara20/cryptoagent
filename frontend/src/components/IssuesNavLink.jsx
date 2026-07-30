import { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { fetchAPI } from '../api';
import { usePolling } from '../hooks/useLive';

export default function IssuesNavLink({ linkClass }) {
  const [count, setCount] = useState(0);

  usePolling(async () => {
    const d = await fetchAPI('/issues');
    setCount(d.open_count || 0);
  }, 10000);

  return (
    <NavLink to="/issues" className={linkClass}>
      Issues
      {count > 0 && (
        <span className="ml-1.5 px-1.5 py-0.5 rounded-full bg-accent-red text-white text-[10px] font-bold">
          {count}
        </span>
      )}
    </NavLink>
  );
}
