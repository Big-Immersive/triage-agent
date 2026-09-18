import { create } from 'zustand'

interface Ui {
  collapsed: boolean
  toggleCollapsed: () => void
  drawerOpen: boolean
  setDrawer: (v: boolean) => void
  switcherOpen: boolean
  setSwitcher: (v: boolean) => void
}
function readCollapsed() { try { return localStorage.getItem('triage.sidebar') === '1' } catch { return false } }
export const useUi = create<Ui>((set) => ({
  collapsed: readCollapsed(),
  toggleCollapsed: () => set((s) => { try { localStorage.setItem('triage.sidebar', s.collapsed ? '0' : '1') } catch { /* */ } return { collapsed: !s.collapsed } }),
  drawerOpen: false,
  setDrawer: (v) => set({ drawerOpen: v }),
  switcherOpen: false,
  setSwitcher: (v) => set({ switcherOpen: v }),
}))
