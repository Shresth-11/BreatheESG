import React, { useState, useEffect, useCallback } from 'react';
import './App.css';
import {
  LayoutDashboard, Upload as UploadIcon, Table2, Lock, AlertTriangle, CheckCircle,
  X, ChevronRight, Zap, Car, Plane, Leaf
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell
} from 'recharts';
import * as api from './api';

// ── Helpers ────────────────────────────────────────────────────────────────
const fmt = (n, d=2) => Number(n || 0).toLocaleString('en-GB', { maximumFractionDigits: d });
const fmtDate = (s) => s ? new Date(s).toLocaleDateString('en-GB', { day:'2-digit', month:'short', year:'numeric' }) : '—';

const StatusBadge = ({ status }) => {
  const icons = { pending: '●', flagged: '⚠', approved: '✓', locked: '🔒' };
  return <span className={`badge ${status}`}>{icons[status]} {status}</span>;
};

const SourceTag = ({ src }) => (
  <span className={`source-tag source-${src}`}>{src}</span>
);

const ScopeDot = ({ scope }) => (
  <span className={`scope-dot scope-${scope}`} />
);

// ── Dashboard ──────────────────────────────────────────────────────────────
function Dashboard({ tenantId }) {
  const [summary, setSummary] = useState(null);

  useEffect(() => {
    if (!tenantId) return;
    api.getSummary(tenantId).then(r => setSummary(r.data)).catch(console.error);
  }, [tenantId]);

  if (!tenantId) return <div className="empty-state"><p>Select a tenant to view the dashboard.</p></div>;
  if (!summary) return <div className="empty-state"><p>Loading…</p></div>;

  const scopeData = [
    { name: 'Scope 1\nDirect', value: Number(summary.by_scope['1']), color: '#fb923c' },
    { name: 'Scope 2\nElectricity', value: Number(summary.by_scope['2']), color: '#60a5fa' },
    { name: 'Scope 3\nIndirect', value: Number(summary.by_scope['3']), color: '#c084fc' },
  ];

  const total = summary.total_co2e_kg;
  const statuses = summary.by_status;

  return (
    <div>
      <div className="grid-4">
        <div className="card">
          <div className="card-title">Total CO₂e</div>
          <div className="card-value">{fmt(total/1000, 1)}<span style={{fontSize:14,fontWeight:400,color:'var(--muted)'}}> t</span></div>
          <div className="card-sub">{fmt(total)} kg across all scopes</div>
        </div>
        <div className="card">
          <div className="card-title">Pending Review</div>
          <div className="card-value" style={{color:'var(--accent)'}}>{statuses.pending}</div>
          <div className="card-sub">{statuses.flagged} flagged</div>
        </div>
        <div className="card">
          <div className="card-title">Approved</div>
          <div className="card-value" style={{color:'#93c5fd'}}>{statuses.approved}</div>
          <div className="card-sub">{statuses.locked} locked for audit</div>
        </div>
        <div className="card">
          <div className="card-title">Total Records</div>
          <div className="card-value">{summary.total_records}</div>
          <div className="card-sub">across 3 sources</div>
        </div>
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-title">Emissions by Scope (kg CO₂e)</div>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={scopeData} margin={{ top: 16, right: 8, bottom: 8, left: 8 }}>
              <XAxis dataKey="name" tick={{ fill: '#8fa894', fontSize: 11 }} />
              <YAxis tick={{ fill: '#8fa894', fontSize: 11 }} />
              <Tooltip
                contentStyle={{ background: '#111a15', border: '1px solid #1e2e20', borderRadius: 8 }}
                labelStyle={{ color: '#e2f0e4' }}
                formatter={(v) => [`${fmt(v)} kg CO₂e`, '']}
              />
              <Bar dataKey="value" radius={[4,4,0,0]}>
                {scopeData.map((d,i) => <Cell key={i} fill={d.color} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
        <div className="card">
          <div className="card-title">Emissions by Source</div>
          {[
            { key: 'sap', label: 'SAP (Fuel & Procurement)', icon: <Car size={14} />, color: '#fb923c' },
            { key: 'utility', label: 'Utility (Electricity)', icon: <Zap size={14} />, color: '#60a5fa' },
            { key: 'travel', label: 'Travel', icon: <Plane size={14} />, color: '#c084fc' },
          ].map(s => {
            const val = Number(summary.by_source[s.key] || 0);
            const pct = total > 0 ? (val / total) * 100 : 0;
            return (
              <div key={s.key} style={{ marginBottom: 16 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 6, color: s.color, fontSize: 13, fontWeight: 600 }}>
                    {s.icon} {s.label}
                  </span>
                  <span className="mono" style={{ color: 'var(--text2)', fontSize: 12 }}>{fmt(val)} kg</span>
                </div>
                <div className="progress-bar-wrap">
                  <div className="progress-bar" style={{ width: `${pct}%`, background: s.color }} />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── Record Detail Modal ────────────────────────────────────────────────────
function RecordModal({ recordId, onClose, onAction }) {
  const [rec, setRec] = useState(null);
  const [note, setNote] = useState('');
  const [flagReason, setFlagReason] = useState('');

  useEffect(() => {
    api.getRecord(recordId).then(r => setRec(r.data)).catch(console.error);
  }, [recordId]);

  const doApprove = async () => {
    await api.approveRecord(recordId, note);
    onAction(); onClose();
  };
  const doFlag = async () => {
    await api.flagRecord(recordId, flagReason || 'Manually flagged by analyst');
    onAction(); onClose();
  };
  const doLock = async () => {
    await api.lockRecord(recordId);
    onAction(); onClose();
  };

  if (!rec) return (
    <div className="modal-overlay"><div className="modal"><p style={{color:'var(--muted)'}}>Loading…</p></div></div>
  );

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}><X size={18}/></button>
        <div className="modal-title">
          <ScopeDot scope={rec.scope} />
          {rec.activity_display} &nbsp;
          <StatusBadge status={rec.status} />
        </div>

        {rec.flag_reason && (
          <div className="flag-banner">
            <AlertTriangle size={14} style={{flexShrink:0,marginTop:1}}/>
            <div><strong>Auto-flagged:</strong> {rec.flag_reason}</div>
          </div>
        )}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
          {[
            ['Source', <SourceTag src={rec.source_type}/>],
            ['Record ID', <span className="mono">{rec.source_row_id || '—'}</span>],
            ['Activity Date', fmtDate(rec.activity_date)],
            ['Facility', rec.facility_id || '—'],
            ['Raw Value', <span className="mono">{fmt(rec.raw_value)} {rec.raw_unit}</span>],
            ['Emission Factor', <span className="mono">{rec.emission_factor} kg CO₂e/{rec.raw_unit} ({rec.emission_factor_source})</span>],
            ['CO₂e', <span className="mono" style={{color:'var(--accent)',fontWeight:600}}>{fmt(rec.co2e_kg)} kg</span>],
            ['Scope', <><ScopeDot scope={rec.scope}/>{rec.scope_display}</>],
          ].map(([label, val]) => (
            <div key={label}>
              <div className="label">{label}</div>
              <div style={{fontSize:13}}>{val}</div>
            </div>
          ))}
        </div>

        <div style={{ marginBottom: 16 }}>
          <div className="label">Raw Source Data</div>
          <div className="raw-data">{JSON.stringify(rec.raw_data, null, 2)}</div>
        </div>

        {rec.status !== 'locked' && (
          <div style={{ marginBottom: 20 }}>
            <label className="label">Analyst Note</label>
            <textarea className="input" value={note} onChange={e => setNote(e.target.value)}
              placeholder="Optional note for audit trail…"/>
            {rec.status === 'approved' ? null : (
              <>
                <label className="label" style={{marginTop:12}}>Flag Reason (if flagging)</label>
                <textarea className="input" value={flagReason} onChange={e => setFlagReason(e.target.value)}
                  placeholder="Why is this record suspicious?"/>
              </>
            )}
          </div>
        )}

        <div className="actions-row">
          {rec.status !== 'locked' && rec.status !== 'approved' && (
            <button className="btn btn-success" onClick={doApprove}><CheckCircle size={14}/> Approve</button>
          )}
          {rec.status !== 'locked' && rec.status !== 'flagged' && (
            <button className="btn btn-warn" onClick={doFlag}><AlertTriangle size={14}/> Flag</button>
          )}
          {rec.status === 'approved' && (
            <button className="btn btn-ghost" onClick={doLock}><Lock size={14}/> Lock for Audit</button>
          )}
          <button className="btn btn-ghost" onClick={onClose}>Close</button>
        </div>

        {rec.audit_logs?.length > 0 && (
          <div className="audit-log">
            <div className="label" style={{marginBottom:8}}>Audit Trail</div>
            {rec.audit_logs.map(log => (
              <div key={log.id} className="audit-item">
                <span className="audit-action">{log.action}</span>
                <span className="audit-time">{fmtDate(log.timestamp)}</span>
                <span style={{color:'var(--text2)'}}>{log.performed_by_name} {log.note && `— ${log.note}`}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Review Table ───────────────────────────────────────────────────────────
function ReviewTable({ tenantId }) {
  const [records, setRecords] = useState([]);
  const [filters, setFilters] = useState({ status: '', scope: '', source_type: '' });
  const [selected, setSelected] = useState(null);
  const [page, setPage] = useState(1);

  const load = useCallback(() => {
    if (!tenantId) return;
    api.getRecords({ tenant: tenantId, ...filters, page }).then(r => setRecords(r.data.results || r.data)).catch(console.error);
  }, [tenantId, filters, page]);

  useEffect(() => { load(); }, [load]);

  if (!tenantId) return <div className="empty-state"><p>Select a tenant.</p></div>;

  return (
    <div>
      {selected && <RecordModal recordId={selected} onClose={() => setSelected(null)} onAction={load} />}
      <div className="filters">
        {[
          { key: 'status', opts: ['', 'pending', 'flagged', 'approved', 'locked'], label: 'Status' },
          { key: 'scope', opts: ['', '1', '2', '3'], label: 'Scope' },
          { key: 'source_type', opts: ['', 'sap', 'utility', 'travel'], label: 'Source' },
        ].map(({ key, opts, label }) => (
          <select key={key} className="filter-select"
            value={filters[key]} onChange={e => setFilters(f => ({ ...f, [key]: e.target.value }))}>
            <option value="">{label}: All</option>
            {opts.filter(Boolean).map(o => <option key={o} value={o}>{o}</option>)}
          </select>
        ))}
      </div>

      <div className="card table-wrap">
        <table>
          <thead>
            <tr>
              <th>Scope</th>
              <th>Source</th>
              <th>Activity</th>
              <th>Date</th>
              <th>Facility</th>
              <th>Raw</th>
              <th>CO₂e (kg)</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {records.length === 0 && (
              <tr><td colSpan={9} style={{textAlign:'center',color:'var(--muted)',padding:40}}>No records found.</td></tr>
            )}
            {records.map(r => (
              <tr key={r.id} style={{ cursor: 'pointer' }} onClick={() => setSelected(r.id)}>
                <td><ScopeDot scope={r.scope}/><span style={{fontSize:11,color:'var(--muted)'}}>{r.scope_display}</span></td>
                <td><SourceTag src={r.source_type}/></td>
                <td style={{maxWidth:160,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{r.activity_type.replace('_',' ')}</td>
                <td className="mono">{fmtDate(r.activity_date)}</td>
                <td className="mono" style={{color:'var(--text2)'}}>{r.facility_id || '—'}</td>
                <td className="mono">{fmt(r.raw_value)} {r.raw_unit}</td>
                <td className="mono" style={{color: r.co2e_kg > 10000 ? 'var(--danger)' : 'var(--accent)'}}>{fmt(r.co2e_kg)}</td>
                <td><StatusBadge status={r.status}/></td>
                <td><ChevronRight size={14} style={{color:'var(--muted)'}}/></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Upload ─────────────────────────────────────────────────────────────────
function Upload({ tenantId }) {
  const [drag, setDrag] = useState(false);
  const [source, setSource] = useState('sap');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const doUpload = async (file) => {
    if (!tenantId) return alert('Select a tenant first.');
    setLoading(true); setResult(null);
    const fd = new FormData();
    fd.append('file', file);
    fd.append('source_type', source);
    fd.append('tenant_id', tenantId);
    try {
      const r = await api.ingestFile(fd);
      setResult({ ok: true, ...r.data });
    } catch (e) {
      setResult({ ok: false, error: e.response?.data?.error || e.message });
    }
    setLoading(false);
  };

  const onDrop = (e) => {
    e.preventDefault(); setDrag(false);
    const f = e.dataTransfer.files[0];
    if (f) doUpload(f);
  };

  const sourceInfo = {
    sap: { title: 'SAP Flat-File Export', desc: 'Semicolon or tab-delimited CSV from SAP MB51/ME2M transaction. Handles German headers, YYYYMMDD dates, inconsistent units (L/KL/GAL/M3).', scope: 'Scope 1' },
    utility: { title: 'Green Button CSV', desc: 'Standard utility portal export (Oracle/PG&E/National Grid format). Columns: TYPE, START DATE, END DATE, USAGE, UNITS, COST.', scope: 'Scope 2' },
    travel: { title: 'Navan / Concur Export', desc: 'CSV with columns: trip_id, traveler_name, trip_type, origin, destination, departure_date, distance_km, nights, transport_mode, cost_usd.', scope: 'Scope 3' },
  };

  return (
    <div>
      <div className="grid-2" style={{ marginBottom: 24 }}>
        {Object.entries(sourceInfo).map(([key, info]) => (
          <div key={key} className="card" style={{
            cursor: 'pointer', border: source === key ? '1px solid var(--accent)' : undefined,
            opacity: source === key ? 1 : 0.6
          }} onClick={() => setSource(key)}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
              <SourceTag src={key} />
              <span style={{ fontSize: 11, color: 'var(--muted)' }}>{info.scope}</span>
            </div>
            <div style={{ fontWeight: 700, marginBottom: 6 }}>{info.title}</div>
            <div style={{ fontSize: 12, color: 'var(--text2)', lineHeight: 1.5 }}>{info.desc}</div>
          </div>
        ))}
      </div>

      <div
        className={`upload-zone ${drag ? 'drag' : ''}`}
        onDragOver={e => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
        onClick={() => document.getElementById('file-input').click()}
      >
        <div className="upload-icon"><UploadIcon size={32}/></div>
        <div className="upload-title">{loading ? 'Processing…' : 'Drop CSV file here or click to browse'}</div>
        <div className="upload-sub">Uploading as: <strong style={{color:'var(--accent)'}}>{sourceInfo[source].title}</strong></div>
        <input id="file-input" type="file" accept=".csv" style={{ display: 'none' }}
          onChange={e => e.target.files[0] && doUpload(e.target.files[0])} />
      </div>

      {result && (
        <div className="card" style={{ marginTop: 20, borderColor: result.ok ? 'var(--accent)' : 'var(--danger)' }}>
          {result.ok ? (
            <>
              <div style={{ color: 'var(--accent)', fontWeight: 700, marginBottom: 12 }}>✓ Ingestion complete</div>
              <div className="grid-4" style={{ marginBottom: 0 }}>
                {[
                  ['Rows ingested', result.rows_ingested],
                  ['Rows failed', result.rows_failed],
                  ['Auto-flagged', result.flagged],
                ].map(([k,v]) => (
                  <div key={k}>
                    <div className="label">{k}</div>
                    <div className="card-value" style={{fontSize:24}}>{v}</div>
                  </div>
                ))}
              </div>
              {result.errors?.length > 0 && (
                <div style={{marginTop:12}}>
                  <div className="label" style={{marginBottom:6}}>Parse Errors (first {result.errors.length})</div>
                  {result.errors.map((e,i) => (
                    <div key={i} className="raw-data" style={{marginBottom:6}}>Row {e.row}: {e.error}</div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div style={{ color: 'var(--danger)' }}>✗ {result.error}</div>
          )}
        </div>
      )}
    </div>
  );
}

// ── App Shell ──────────────────────────────────────────────────────────────
export default function App() {
  const [page, setPage] = useState('dashboard');
  const [tenants, setTenants] = useState([]);
  const [tenantId, setTenantId] = useState('');

  useEffect(() => {
    api.getTenants().then(r => {
      const list = r.data.results || r.data;
      setTenants(list);
      if (list.length > 0) setTenantId(list[0].id);
    }).catch(console.error);
  }, []);

  const nav = [
    { id: 'dashboard', label: 'Dashboard', icon: <LayoutDashboard size={15}/> },
    { id: 'review', label: 'Review Records', icon: <Table2 size={15}/> },
    { id: 'upload', label: 'Upload Data', icon: <UploadIcon size={15}/> },
  ];

  const pageTitles = {
    dashboard: ['Emissions Dashboard', 'Overview of all ingested carbon data'],
    review: ['Review Records', 'Approve, flag, or lock emission records'],
    upload: ['Ingest Data', 'Upload CSV files from SAP, utility portals, or travel platforms'],
  };

  const [title, sub] = pageTitles[page];

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <Leaf size={18} style={{display:'inline',marginRight:6}}/>
          BreatheESG
          <span>Carbon Intelligence</span>
        </div>
        <nav className="nav">
          {nav.map(n => (
            <button key={n.id} className={`nav-item ${page===n.id?'active':''}`} onClick={() => setPage(n.id)}>
              {n.icon} {n.label}
            </button>
          ))}
        </nav>
        <div className="tenant-select">
          <div className="label" style={{marginBottom:6}}>Client Tenant</div>
          <select value={tenantId} onChange={e => setTenantId(e.target.value)}>
            {tenants.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        </div>
      </aside>

      <main className="main">
        <div className="page-header">
          <div className="page-title">{title}</div>
          <div className="page-sub">{sub}</div>
        </div>
        {page === 'dashboard' && <Dashboard tenantId={tenantId}/>}
        {page === 'review' && <ReviewTable tenantId={tenantId}/>}
        {page === 'upload' && <Upload tenantId={tenantId}/>}
      </main>
    </div>
  );
}
