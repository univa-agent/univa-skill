"use client";

import React, { useState, useEffect } from 'react';
import { 
  Search, Plus, Download, Upload, Trash2, Edit, 
  RefreshCw, Key, CheckCircle, XCircle, AlertCircle,
  BarChart3, Users, Activity
} from 'lucide-react';

// Use Next.js API routes instead of direct backend access
const API_BASE_URL = '/api';

interface AccessCode {
  access_code: string;
  user_id: string;
  description: string;
  created_at: string;
  enabled: boolean;
  last_used: string | null;
  usage_count: number;
  max_conversations: number | null;
  conversation_count: number;
}

interface Stats {
  total_codes: number;
  enabled_codes: number;
  disabled_codes: number;
  limited_codes: number;
  unlimited_codes: number;
  exhausted_codes: number;
  total_usage: number;
  total_conversations: number;
  recent_used: AccessCode[];
}

export default function AdminAccessCodesPage() {
  const [accessCodes, setAccessCodes] = useState<AccessCode[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterEnabled, setFilterEnabled] = useState<boolean | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [totalCodes, setTotalCodes] = useState(0);
  const [selectedCodes, setSelectedCodes] = useState<Set<string>>(new Set());
  const [adminCode, setAdminCode] = useState('');
  const [tempAdminCode, setTempAdminCode] = useState('');
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showBatchCreateModal, setShowBatchCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingCode, setEditingCode] = useState<AccessCode | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const pageSize = 20;

  // No longer use localStorage, manual login required each time

  // Load access code list
  const loadAccessCodes = async () => {
    if (!adminCode) {
      setError('Please enter the admin access code first');
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError(null);

      const params = new URLSearchParams({
        skip: ((currentPage - 1) * pageSize).toString(),
        limit: pageSize.toString(),
      });

      if (searchTerm) params.append('search', searchTerm);
      if (filterEnabled !== null) params.append('enabled', filterEnabled.toString());

      const response = await fetch(`${API_BASE_URL}/admin/access-codes?${params}`, {
        headers: {
          'X-Access-Code': adminCode,
        },
      });

      if (!response.ok) {
        throw new Error('Failed to load access codes');
      }

      const data = await response.json();
      setAccessCodes(data.codes || []);
      setTotalCodes(data.total || 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load');
    } finally {
      setLoading(false);
    }
  };

  // Load statistics
  const loadStats = async () => {
    if (!adminCode) return;

    try {
      const response = await fetch(`${API_BASE_URL}/admin/access-codes/stats`, {
        headers: {
          'X-Access-Code': adminCode,
        },
      });

      if (response.ok) {
        const data = await response.json();
        setStats(data);
      }
    } catch (err) {
      console.error('Failed to load statistics:', err);
    }
  };

  // Load data only after login and when page parameters change
  useEffect(() => {
    if (isLoggedIn && adminCode) {
      loadAccessCodes();
      loadStats();
    }
  }, [isLoggedIn, currentPage, searchTerm, filterEnabled]);

  // Save admin access code and login (simplified version, no localStorage)
  const handleSaveAdminCode = async () => {
    if (!tempAdminCode.trim()) {
      setError('Please enter the admin access code');
      return;
    }
    
    // Verify if access code is valid
    try {
      setLoading(true);
      setError(null);
      
      // Try to get statistics to verify access code
      const response = await fetch(`${API_BASE_URL}/admin/access-codes/stats`, {
        headers: {
          'X-Access-Code': tempAdminCode,
        },
      });
      
      if (!response.ok) {
        if (response.status === 403) {
          setError('Invalid admin access code, please check and try again');
        } else {
          setError('Verification failed, please try again later');
        }
        setLoading(false);
        return;
      }
      
      // Verification successful, login directly (not saved to localStorage)
      setAdminCode(tempAdminCode);
      setIsLoggedIn(true);
      setLoading(false);
    } catch (err) {
      setError('Network error, please check if the backend server is running');
      setLoading(false);
    }
  };

  // Create access code
  const handleCreateCode = async (formData: {
    user_id: string;
    description: string;
    max_conversations: number | null;
  }) => {
    try {
      const response = await fetch(`${API_BASE_URL}/admin/access-codes`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Access-Code': adminCode,
        },
        body: JSON.stringify(formData),
      });

      if (!response.ok) throw new Error('Failed to create');

      setSuccess('Access code created successfully');
      setShowCreateModal(false);
      loadAccessCodes();
      loadStats();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create');
    }
  };

  // Batch create access codes
  const handleBatchCreate = async (formData: {
    count: number;
    user_id_prefix: string;
    description: string;
    max_conversations: number | null;
  }) => {
    try {
      const response = await fetch(`${API_BASE_URL}/admin/access-codes/batch`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Access-Code': adminCode,
        },
        body: JSON.stringify(formData),
      });

      if (!response.ok) throw new Error('Batch creation failed');

      const data = await response.json();
      setSuccess(`Successfully created ${data.count} access codes`);
      setShowBatchCreateModal(false);
      loadAccessCodes();
      loadStats();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Batch creation failed');
    }
  };

  // Update access code
  const handleUpdateCode = async (code: string, updates: {
    description?: string;
    enabled?: boolean;
    max_conversations?: number | null;
  }) => {
    try {
      const response = await fetch(`${API_BASE_URL}/admin/access-codes/${code}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'X-Access-Code': adminCode,
        },
        body: JSON.stringify(updates),
      });

      if (!response.ok) throw new Error('Failed to update');

      setSuccess('Access code updated successfully');
      setShowEditModal(false);
      setEditingCode(null);
      loadAccessCodes();
      loadStats();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update');
    }
  };

  // Delete access code
  const handleDeleteCode = async (code: string) => {
    if (!confirm('Are you sure you want to delete this access code?')) return;

    try {
      const response = await fetch(`${API_BASE_URL}/admin/access-codes/${code}`, {
        method: 'DELETE',
        headers: {
          'X-Access-Code': adminCode,
        },
      });

      if (!response.ok) throw new Error('Failed to delete');

      setSuccess('Access code deleted successfully');
      loadAccessCodes();
      loadStats();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete');
    }
  };

  // Batch delete
  const handleBatchDelete = async () => {
    if (selectedCodes.size === 0) {
      setError('Please select access codes to delete first');
      return;
    }

    if (!confirm(`Are you sure you want to delete ${selectedCodes.size} selected access codes?`)) return;

    try {
      const response = await fetch(`${API_BASE_URL}/admin/access-codes/batch-delete`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Access-Code': adminCode,
        },
        body: JSON.stringify({ access_codes: Array.from(selectedCodes) }),
      });

      if (!response.ok) throw new Error('Batch deletion failed');

      const data = await response.json();
      setSuccess(`Successfully deleted ${data.deleted_count} access codes`);
      setSelectedCodes(new Set());
      loadAccessCodes();
      loadStats();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Batch deletion failed');
    }
  };

  // Export access codes
  const handleExport = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/admin/access-codes/export/json`, {
        headers: {
          'X-Access-Code': adminCode,
        },
      });

      if (!response.ok) throw new Error('Failed to export');

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `access_codes_${new Date().toISOString().split('T')[0]}.json`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      setSuccess('Access codes exported successfully');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to export');
    }
  };

  // Import access codes
  const handleImport = async (file: File, overwrite: boolean) => {
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      const codes = data.codes || [];

      const response = await fetch(`${API_BASE_URL}/admin/access-codes/import/json`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Access-Code': adminCode,
        },
        body: JSON.stringify({ codes, overwrite }),
      });

      if (!response.ok) throw new Error('Failed to import');

      const result = await response.json();
      setSuccess(`Successfully imported ${result.imported_count} access codes, skipped ${result.skipped_count}`);
      loadAccessCodes();
      loadStats();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to import');
    }
  };

  // Toggle selection
  const toggleSelect = (code: string) => {
    const newSelected = new Set(selectedCodes);
    if (newSelected.has(code)) {
      newSelected.delete(code);
    } else {
      newSelected.add(code);
    }
    setSelectedCodes(newSelected);
  };

  // Select all / Deselect all
  const toggleSelectAll = () => {
    if (selectedCodes.size === accessCodes.length) {
      setSelectedCodes(new Set());
    } else {
      setSelectedCodes(new Set(accessCodes.map(c => c.access_code)));
    }
  };

  if (!adminCode) {
    return (
      <div className="min-h-screen bg-gray-900 flex items-center justify-center p-4">
        <div className="bg-gray-800 rounded-lg shadow-xl max-w-md w-full p-6">
          <div className="flex items-center gap-3 mb-6">
            <Key className="w-8 h-8 text-blue-400" />
            <h1 className="text-2xl font-bold text-white">Admin Login</h1>
          </div>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Admin Access Code
              </label>
              <input
                type="password"
                value={tempAdminCode}
                onChange={(e) => {
                  setTempAdminCode(e.target.value);
                  setError(null); // Clear error
                }}
                placeholder="Please enter admin access code"
                className="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                onKeyPress={(e) => e.key === 'Enter' && !loading && handleSaveAdminCode()}
                disabled={loading}
              />
            </div>
            
            {/* Error message */}
            {error && (
              <div className="p-3 bg-red-900 bg-opacity-50 border border-red-700 rounded-lg flex items-start gap-2">
                <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                <p className="text-sm text-red-200">{error}</p>
              </div>
            )}
            
            <button
              onClick={handleSaveAdminCode}
              disabled={loading || !tempAdminCode.trim()}
              className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-colors"
            >
              {loading ? 'Verifying...' : 'Login'}
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-900 p-6">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-white mb-2">Access Code Management</h1>
          <p className="text-gray-400">Manage and monitor all access codes</p>
        </div>

        {/* Statistics cards */}
        {stats && (
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
            <StatCard
              icon={<Key className="w-6 h-6" />}
              title="Total Access Codes"
              value={stats.total_codes}
              color="blue"
            />
            <StatCard
              icon={<CheckCircle className="w-6 h-6" />}
              title="Enabled"
              value={stats.enabled_codes}
              color="green"
            />
            <StatCard
              icon={<Activity className="w-6 h-6" />}
              title="Total Usage"
              value={stats.total_usage}
              color="purple"
            />
            <StatCard
              icon={<Users className="w-6 h-6" />}
              title="Total Conversations"
              value={stats.total_conversations}
              color="orange"
            />
          </div>
        )}

        {/* Error and success messages */}
        {error && (
          <div className="mb-4 p-4 bg-red-900 bg-opacity-50 border border-red-700 rounded-lg flex items-start gap-2">
            <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-red-200">{error}</p>
            </div>
            <button onClick={() => setError(null)} className="text-red-400 hover:text-red-300">
              ×
            </button>
          </div>
        )}

        {success && (
          <div className="mb-4 p-4 bg-green-900 bg-opacity-50 border border-green-700 rounded-lg flex items-start gap-2">
            <CheckCircle className="w-5 h-5 text-green-400 flex-shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-green-200">{success}</p>
            </div>
            <button onClick={() => setSuccess(null)} className="text-green-400 hover:text-green-300">
              ×
            </button>
          </div>
        )}

        {/* Toolbar */}
        <div className="bg-gray-800 rounded-lg p-4 mb-6">
          <div className="flex flex-col md:flex-row gap-4">
            {/* Search */}
            <div className="flex-1">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
                <input
                  type="text"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  placeholder="Search user ID, description or access code..."
                  className="w-full pl-10 pr-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>

            {/* Filter */}
            <select
              value={filterEnabled === null ? 'all' : filterEnabled.toString()}
              onChange={(e) => setFilterEnabled(e.target.value === 'all' ? null : e.target.value === 'true')}
              className="px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="all">All Status</option>
              <option value="true">Enabled</option>
              <option value="false">Disabled</option>
            </select>

            {/* Action buttons */}
            <div className="flex gap-2">
              <button
                onClick={() => setShowCreateModal(true)}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg flex items-center gap-2 transition-colors"
              >
                <Plus className="w-5 h-5" />
                Create
              </button>
              <button
                onClick={() => setShowBatchCreateModal(true)}
                className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg flex items-center gap-2 transition-colors"
              >
                <Plus className="w-5 h-5" />
                Batch Create
              </button>
              <button
                onClick={handleExport}
                className="px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg flex items-center gap-2 transition-colors"
              >
                <Download className="w-5 h-5" />
                Export
              </button>
              <label className="px-4 py-2 bg-orange-600 hover:bg-orange-700 text-white rounded-lg flex items-center gap-2 transition-colors cursor-pointer">
                <Upload className="w-5 h-5" />
                Import
                <input
                  type="file"
                  accept=".json"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) {
                      const overwrite = confirm('Overwrite existing access codes?');
                      handleImport(file, overwrite);
                    }
                  }}
                />
              </label>
              {selectedCodes.size > 0 && (
                <button
                  onClick={handleBatchDelete}
                  className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg flex items-center gap-2 transition-colors"
                >
                  <Trash2 className="w-5 h-5" />
                  Delete Selected ({selectedCodes.size})
                </button>
              )}
              <button
                onClick={() => {
                  loadAccessCodes();
                  loadStats();
                }}
                className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg flex items-center gap-2 transition-colors"
              >
                <RefreshCw className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>

        {/* Access code table */}
        <div className="bg-gray-800 rounded-lg overflow-hidden">
          {loading ? (
            <div className="p-8 text-center text-gray-400">Loading...</div>
          ) : accessCodes.length === 0 ? (
            <div className="p-8 text-center text-gray-400">No access codes found</div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-700">
                    <tr>
                      <th className="px-4 py-3 text-left">
                        <input
                          type="checkbox"
                          checked={selectedCodes.size === accessCodes.length && accessCodes.length > 0}
                          onChange={toggleSelectAll}
                          className="rounded"
                        />
                      </th>
                      <th className="px-4 py-3 text-left text-sm font-medium text-gray-300">User ID</th>
                      <th className="px-4 py-3 text-left text-sm font-medium text-gray-300">Access Code</th>
                      <th className="px-4 py-3 text-left text-sm font-medium text-gray-300">Description</th>
                      <th className="px-4 py-3 text-left text-sm font-medium text-gray-300">Status</th>
                      <th className="px-4 py-3 text-left text-sm font-medium text-gray-300">Conversations</th>
                      <th className="px-4 py-3 text-left text-sm font-medium text-gray-300">Usage Count</th>
                      <th className="px-4 py-3 text-left text-sm font-medium text-gray-300">Last Used</th>
                      <th className="px-4 py-3 text-left text-sm font-medium text-gray-300">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-700">
                    {accessCodes.map((code) => (
                      <tr key={code.access_code} className="hover:bg-gray-750">
                        <td className="px-4 py-3">
                          <input
                            type="checkbox"
                            checked={selectedCodes.has(code.access_code)}
                            onChange={() => toggleSelect(code.access_code)}
                            className="rounded"
                          />
                        </td>
                        <td className="px-4 py-3 text-sm text-white">{code.user_id}</td>
                        <td className="px-4 py-3 text-sm text-gray-300 font-mono">
                          {code.access_code.substring(0, 8)}...
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-300">{code.description || '-'}</td>
                        <td className="px-4 py-3">
                          {code.enabled ? (
                            <span className="px-2 py-1 bg-green-900 bg-opacity-50 text-green-400 text-xs rounded-full">
                              Enabled
                            </span>
                          ) : (
                            <span className="px-2 py-1 bg-red-900 bg-opacity-50 text-red-400 text-xs rounded-full">
                              Disabled
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-300">
                          {code.conversation_count}
                          {code.max_conversations !== null && ` / ${code.max_conversations}`}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-300">{code.usage_count}</td>
                        <td className="px-4 py-3 text-sm text-gray-300">
                          {code.last_used ? new Date(code.last_used).toLocaleString('zh-CN') : '-'}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex gap-2">
                            <button
                              onClick={() => {
                                setEditingCode(code);
                                setShowEditModal(true);
                              }}
                              className="p-1 text-blue-400 hover:text-blue-300"
                              title="Edit"
                            >
                              <Edit className="w-4 h-4" />
                            </button>
                            <button
                              onClick={() => handleDeleteCode(code.access_code)}
                              className="p-1 text-red-400 hover:text-red-300"
                              title="Delete"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              <div className="px-4 py-3 bg-gray-750 border-t border-gray-700 flex items-center justify-between">
                <div className="text-sm text-gray-400">
                  Showing {(currentPage - 1) * pageSize + 1} - {Math.min(currentPage * pageSize, totalCodes)} / Total {totalCodes}
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                    disabled={currentPage === 1}
                    className="px-3 py-1 bg-gray-700 hover:bg-gray-600 disabled:bg-gray-800 disabled:text-gray-600 text-white rounded transition-colors"
                  >
                    Previous
                  </button>
                  <button
                    onClick={() => setCurrentPage(p => p + 1)}
                    disabled={currentPage * pageSize >= totalCodes}
                    className="px-3 py-1 bg-gray-700 hover:bg-gray-600 disabled:bg-gray-800 disabled:text-gray-600 text-white rounded transition-colors"
                  >
                    Next
                  </button>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Create modal */}
        {showCreateModal && (
          <CreateModal
            onClose={() => setShowCreateModal(false)}
            onCreate={handleCreateCode}
          />
        )}

        {/* Batch create modal */}
        {showBatchCreateModal && (
          <BatchCreateModal
            onClose={() => setShowBatchCreateModal(false)}
            onCreate={handleBatchCreate}
          />
        )}

        {/* Edit modal */}
        {showEditModal && editingCode && (
          <EditModal
            code={editingCode}
            onClose={() => {
              setShowEditModal(false);
              setEditingCode(null);
            }}
            onUpdate={handleUpdateCode}
          />
        )}
      </div>
    </div>
  );
}

// Statistics card component
function StatCard({ icon, title, value, color }: {
  icon: React.ReactNode;
  title: string;
  value: number;
  color: 'blue' | 'green' | 'purple' | 'orange';
}) {
  const colorClasses = {
    blue: 'bg-blue-900 bg-opacity-50 border-blue-700 text-blue-400',
    green: 'bg-green-900 bg-opacity-50 border-green-700 text-green-400',
    purple: 'bg-purple-900 bg-opacity-50 border-purple-700 text-purple-400',
    orange: 'bg-orange-900 bg-opacity-50 border-orange-700 text-orange-400',
  };

  return (
    <div className={`${colorClasses[color]} border rounded-lg p-4`}>
      <div className="flex items-center gap-3">
        <div className="p-2 bg-gray-800 rounded-lg">
          {icon}
        </div>
        <div>
          <p className="text-sm text-gray-400">{title}</p>
          <p className="text-2xl font-bold text-white">{value}</p>
        </div>
      </div>
    </div>
  );
}

// Create modal component
function CreateModal({ onClose, onCreate }: {
  onClose: () => void;
  onCreate: (data: any) => void;
}) {
  const [formData, setFormData] = useState({
    user_id: '',
    description: '',
    max_conversations: '' as string,
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onCreate({
      user_id: formData.user_id,
      description: formData.description,
      max_conversations: formData.max_conversations ? parseInt(formData.max_conversations) : null,
    });
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-800 rounded-lg shadow-xl max-w-md w-full">
        <div className="p-6">
          <h2 className="text-xl font-bold text-white mb-4">Create Access Code</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                User ID *
              </label>
              <input
                type="text"
                value={formData.user_id}
                onChange={(e) => setFormData({ ...formData, user_id: e.target.value })}
                required
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Description
              </label>
              <input
                type="text"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Max Conversations (leave blank for unlimited)
              </label>
              <input
                type="number"
                value={formData.max_conversations}
                onChange={(e) => setFormData({ ...formData, max_conversations: e.target.value })}
                min="1"
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="flex gap-2 pt-4">
              <button
                type="button"
                onClick={onClose}
                className="flex-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
              >
                Create
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

// Batch create modal component
function BatchCreateModal({ onClose, onCreate }: {
  onClose: () => void;
  onCreate: (data: any) => void;
}) {
  const [formData, setFormData] = useState({
    count: '10',
    user_id_prefix: 'user',
    description: '',
    max_conversations: '' as string,
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onCreate({
      count: parseInt(formData.count),
      user_id_prefix: formData.user_id_prefix,
      description: formData.description,
      max_conversations: formData.max_conversations ? parseInt(formData.max_conversations) : null,
    });
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-800 rounded-lg shadow-xl max-w-md w-full">
        <div className="p-6">
          <h2 className="text-xl font-bold text-white mb-4">Batch Create Access Codes</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Quantity * (1-100)
              </label>
              <input
                type="number"
                value={formData.count}
                onChange={(e) => setFormData({ ...formData, count: e.target.value })}
                required
                min="1"
                max="100"
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                User ID Prefix *
              </label>
              <input
                type="text"
                value={formData.user_id_prefix}
                onChange={(e) => setFormData({ ...formData, user_id_prefix: e.target.value })}
                required
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <p className="mt-1 text-xs text-gray-400">
                Will generate {formData.user_id_prefix}_1, {formData.user_id_prefix}_2, ...
              </p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Description
              </label>
              <input
                type="text"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Max Conversations (leave blank for unlimited)
              </label>
              <input
                type="number"
                value={formData.max_conversations}
                onChange={(e) => setFormData({ ...formData, max_conversations: e.target.value })}
                min="1"
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div className="flex gap-2 pt-4">
              <button
                type="button"
                onClick={onClose}
                className="flex-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="flex-1 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg transition-colors"
              >
                Batch Create
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}

// Edit modal component
function EditModal({ code, onClose, onUpdate }: {
  code: AccessCode;
  onClose: () => void;
  onUpdate: (code: string, updates: any) => void;
}) {
  const [formData, setFormData] = useState({
    description: code.description,
    enabled: code.enabled,
    max_conversations: code.max_conversations?.toString() || '' as string,
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onUpdate(code.access_code, {
      description: formData.description,
      enabled: formData.enabled,
      max_conversations: formData.max_conversations ? parseInt(formData.max_conversations) : null,
    });
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-gray-800 rounded-lg shadow-xl max-w-md w-full">
        <div className="p-6">
          <h2 className="text-xl font-bold text-white mb-4">Edit Access Code</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                User ID
              </label>
              <input
                type="text"
                value={code.user_id}
                disabled
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-gray-400"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Access Code
              </label>
              <input
                type="text"
                value={code.access_code}
                disabled
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-gray-400 font-mono text-sm"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Description
              </label>
              <input
                type="text"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="flex items-center gap-2 text-sm font-medium text-gray-300">
                <input
                  type="checkbox"
                  checked={formData.enabled}
                  onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
                  className="rounded"
                />
                Enable Access Code
              </label>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-300 mb-2">
                Max Conversations (leave blank for unlimited)
              </label>
              <input
                type="number"
                value={formData.max_conversations}
                onChange={(e) => setFormData({ ...formData, max_conversations: e.target.value })}
                min="1"
                className="w-full px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <p className="mt-1 text-xs text-gray-400">
                Currently used: {code.conversation_count} times
              </p>
            </div>
            <div className="flex gap-2 pt-4">
              <button
                type="button"
                onClick={onClose}
                className="flex-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="flex-1 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
              >
                Save
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}