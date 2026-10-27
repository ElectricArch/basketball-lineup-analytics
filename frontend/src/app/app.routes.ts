import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'lineups-summary' },
  {
    path: 'lineups-summary',
    loadComponent: () =>
      import('./lineups-summary/lineups-summary.component').then((m) => m.LineupsSummaryComponent),
  },
  { path: '**', redirectTo: 'lineups-summary' },
];
