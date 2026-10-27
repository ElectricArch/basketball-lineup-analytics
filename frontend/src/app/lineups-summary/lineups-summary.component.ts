import { DecimalPipe, PercentPipe } from '@angular/common';
import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatTableModule } from '@angular/material/table';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Subject, catchError, debounceTime, distinctUntilChanged, map, merge, of, startWith, switchMap } from 'rxjs';
import { CatalogPlayer, LineupQueryOptions, LineupSortField, LineupSummary, LineupTeam, SortOrder } from '../_models/lineup';
import { LineupsService } from '../_services/lineups.service';

interface MetricColumn {
  field: LineupSortField;
  label: string;
  description: string;
  format: 'integer' | 'rating' | 'percent';
}

@Component({
  selector: 'lineups-summary-component',
  imports: [DecimalPipe, PercentPipe, ReactiveFormsModule, MatFormFieldModule, MatInputModule, MatTableModule, MatTooltipModule],
  templateUrl: './lineups-summary.component.html',
  styleUrl: './lineups-summary.component.scss',
})
export class LineupsSummaryComponent implements OnInit {
  private readonly lineupsService = inject(LineupsService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly refresh = new Subject<void>();

  readonly form = new FormGroup({
    lineup_size: new FormControl(5, { nonNullable: true }),
    team_id: new FormControl('', { nonNullable: true }),
    player_id: new FormControl('', { nonNullable: true }),
    min_possessions: new FormControl(10, { nonNullable: true }),
    sort_by: new FormControl<LineupSortField>('net_rating', { nonNullable: true }),
    sort_order: new FormControl<SortOrder>('desc', { nonNullable: true }),
    limit: new FormControl(25, { nonNullable: true }),
  });
  readonly lineupSizes = [1, 2, 3, 4, 5];
  readonly limits = [10, 25, 50, 100];
  readonly loading = signal(true);
  readonly error = signal(false);
  readonly catalogLoading = signal(true);
  readonly catalogError = signal(false);
  readonly teams = signal<LineupTeam[]>([]);
  readonly catalogPlayers = signal<CatalogPlayer[]>([]);
  readonly selectedTeam = signal('');
  readonly lineups = signal<LineupSummary[]>([]);
  readonly availablePlayers = computed(() => this.catalogPlayers().filter(
    player => !this.selectedTeam() || player.team_id === this.selectedTeam(),
  ));
  readonly metrics: MetricColumn[] = [
    { field: 'total_possessions', label: 'Possessions', description: 'Total offensive and defensive possessions.', format: 'integer' },
    { field: 'offensive_rating', label: 'Off Rating', description: 'Points scored per 100 offensive possessions. Higher is better.', format: 'rating' },
    { field: 'defensive_rating', label: 'Def Rating', description: 'Opponent points allowed per 100 defensive possessions. Lower is better.', format: 'rating' },
    { field: 'net_rating', label: 'Net Rating', description: 'Offensive rating minus defensive rating. Higher is better.', format: 'rating' },
    { field: 'offensive_efg_pct', label: 'Off eFG%', description: 'Effective field-goal percentage; accounts for the added value of three-pointers.', format: 'percent' },
    { field: 'defensive_efg_pct', label: 'Def eFG%', description: 'Opponent effective field-goal percentage. Lower is better.', format: 'percent' },
    { field: 'offensive_rebound_pct', label: 'Off Reb%', description: 'Offensive rebounds divided by offensive rebound opportunities.', format: 'percent' },
    { field: 'defensive_rebound_pct', label: 'Def Reb%', description: 'Defensive rebounds divided by defensive rebound opportunities.', format: 'percent' },
    { field: 'offensive_turnover_rate', label: 'TOV / 100', description: 'Turnovers per 100 offensive possessions. Lower is better.', format: 'rating' },
    { field: 'opponent_turnover_rate', label: 'Opp TOV / 100', description: 'Opponent turnovers forced per 100 defensive possessions. Higher is better.', format: 'rating' },
  ];
  readonly columns = ['team', 'lineup', ...this.metrics.map(metric => metric.field)];
  readonly sortOptions: { value: LineupSortField; label: string }[] = [
    ...this.metrics.map(metric => ({ value: metric.field, label: metric.label })),
    { value: 'offensive_possessions', label: 'Offensive Possessions' },
    { value: 'defensive_possessions', label: 'Defensive Possessions' },
  ];
  readonly highlights = computed(() => {
    const rows = this.lineups();
    const first = rows[0];
    if (!first) return [];
    return ([
      { label: 'Best Net Rating', field: 'net_rating', lower: false, note: 'Points per 100 possessions' },
      { label: 'Best Offensive Rating', field: 'offensive_rating', lower: false, note: 'Points scored per 100' },
      { label: 'Best Defensive Rating', field: 'defensive_rating', lower: true, note: 'Points allowed per 100 · lower is better' },
    ] as const).map(metric => {
      const lineup = rows.reduce((best, row) => (
        metric.lower ? row[metric.field] < best[metric.field] : row[metric.field] > best[metric.field]
      ) ? row : best, first);
      return { ...metric, lineup, value: lineup[metric.field] };
    });
  });

  ngOnInit(): void {
    this.loadCatalog();
    const changes = this.form.valueChanges.pipe(
      debounceTime(250),
      startWith(this.form.getRawValue()),
      map(() => this.queryOptions()),
      distinctUntilChanged((previous, current) => JSON.stringify(previous) === JSON.stringify(current)),
    );
    merge(changes, this.refresh.pipe(map(() => this.queryOptions()))).pipe(
      switchMap(options => {
        this.loading.set(true);
        this.error.set(false);
        this.lineups.set([]);
        return this.lineupsService.getLineupsLeagueSummary(options).pipe(
          map(response => ({ rows: response.apiResponse, failed: false })),
          catchError(() => of({ rows: [] as LineupSummary[], failed: true })),
        );
      }),
      takeUntilDestroyed(this.destroyRef),
    ).subscribe(result => {
      this.lineups.set(result.rows);
      this.error.set(result.failed);
      this.loading.set(false);
    });
  }

  loadCatalog(): void {
    this.catalogLoading.set(true);
    this.catalogError.set(false);
    this.lineupsService.getLineupsLeagueSummary({ lineup_size: 1, limit: 100 }).pipe(
      takeUntilDestroyed(this.destroyRef),
    ).subscribe({
      next: response => {
        const teams = new Map<string, LineupTeam>();
        const players = new Map<string, CatalogPlayer>();
        for (const lineup of response.apiResponse) {
          teams.set(lineup.team_id, { team_id: lineup.team_id, team_name: lineup.team_name });
          for (const player of lineup.players) players.set(player.player_id, { ...player, team_id: lineup.team_id });
        }
        this.teams.set([...teams.values()].sort((a, b) => a.team_name.localeCompare(b.team_name)));
        this.catalogPlayers.set([...players.values()].sort((a, b) => a.name.localeCompare(b.name)));
        this.catalogLoading.set(false);
      },
      error: () => { this.catalogError.set(true); this.catalogLoading.set(false); },
    });
  }

  retry(): void { this.refresh.next(); }

  resetFilters(): void {
    this.form.reset({ lineup_size: 5, team_id: '', player_id: '', min_possessions: 10,
      sort_by: 'net_rating', sort_order: 'desc', limit: 25 });
  }

  playerNames(lineup: LineupSummary): string {
    return lineup.players.map(player => player.name).join(' · ');
  }

  private queryOptions(): LineupQueryOptions {
    const values = this.form.getRawValue();
    this.selectedTeam.set(values.team_id);
    if (values.team_id && values.player_id && !this.catalogPlayers().some(
      player => player.player_id === values.player_id && player.team_id === values.team_id,
    )) {
      this.form.controls.player_id.setValue('', { emitEvent: false });
      values.player_id = '';
    }
    const minimum = Math.max(0, Math.trunc(Number(values.min_possessions) || 0));
    if (values.min_possessions !== minimum) {
      this.form.controls.min_possessions.setValue(minimum, { emitEvent: false });
    }
    return { ...values, min_possessions: minimum };
  }
}
