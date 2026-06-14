import { Outlet, Link, NavLink, useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <>
      <nav className="nav">
        <Link to="/" className="nav-brand">🏠 CleanSplit</Link>
        <div className="nav-links">
          <NavLink to="/" end>Groups</NavLink>
        </div>
        <div className="nav-user">
          <span className="text-muted text-sm">{user?.name}</span>
          <button className="btn btn-outline btn-sm" onClick={handleLogout}>Log out</button>
        </div>
      </nav>
      <Outlet />
    </>
  );
}
