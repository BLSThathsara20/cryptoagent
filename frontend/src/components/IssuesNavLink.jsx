import { useState, useEffect } from 'react';
import { NavLink } from 'react-router-dom';
import { fetchAPI } from '../api';

export default function IssuesNavLink({ linkClass }) {
  const [count, setCount] = useState(0);

  useEffect(() => {
    const load = () => fetchAPI('/issues').then((d) => setCount(d.open_count || 0)).catch(() => {});
    load();
    const interval = setInterval(load, 30000);
    return () => clearInterval(interval);
  }, []);

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
