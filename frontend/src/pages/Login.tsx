import { useState, FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { authApi } from '../api';
import { useAuth } from '../context/AuthContext';

export default function Login() {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const res = mode === 'login'
        ? await authApi.login(email, password)
        : await authApi.register(name, email, password);
      login(res.data.access_token, res.data.user);
      navigate('/');
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Something went wrong');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page-sm">
      <div className="card">
        <div style={{ textAlign: 'center', marginBottom: 24 }}>
          <div style={{ fontSize: 40, marginBottom: 8 }}>🏠</div>
          <h1 style={{ fontSize: 22, fontWeight: 700 }}>CleanSplit</h1>
          <p className="text-muted text-sm">Shared expenses, zero arguments</p>
        </div>

        <div className="flex-gap mb-2" style={{ justifyContent: 'center' }}>
          <button
            className={`btn ${mode === 'login' ? 'btn-primary' : 'btn-outline'}`}
            onClick={() => setMode('login')}
          >Log in</button>
          <button
            className={`btn ${mode === 'register' ? 'btn-primary' : 'btn-outline'}`}
            onClick={() => setMode('register')}
          >Register</button>
        </div>

        <form onSubmit={submit}>
          {mode === 'register' && (
            <div className="form-group">
              <label>Name</label>
              <input className="input" value={name} onChange={e => setName(e.target.value)}
                required placeholder="Aisha" />
            </div>
          )}
          <div className="form-group">
            <label>Email</label>
            <input className="input" type="email" value={email}
              onChange={e => setEmail(e.target.value)} required placeholder="you@example.com" />
          </div>
          <div className="form-group">
            <label>Password</label>
            <input className="input" type="password" value={password}
              onChange={e => setPassword(e.target.value)} required />
          </div>
          {error && <p className="text-red text-sm mb-1">{error}</p>}
          <button className="btn btn-primary" style={{ width: '100%' }}
            type="submit" disabled={loading}>
            {loading ? 'Please wait…' : mode === 'login' ? 'Log in' : 'Create account'}
          </button>
        </form>
      </div>
    </div>
  );
}
