import { render, screen } from '@testing-library/react';
import { describe, it, expect, beforeAll, vi } from 'vitest';
import App from './App';

// Mock matchMedia if needed by Lucide/React
beforeAll(() => {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockImplementation(query => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(), // deprecated
      removeListener: vi.fn(), // deprecated
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

describe('App Component', () => {
  it('renders the header and navigation links', () => {
    render(<App />);
    
    // Header text
    expect(screen.getByText('Atom-Terminal-Pet')).toBeInTheDocument();
    
    // Navigation links
    expect(screen.getByText('Flasher')).toBeInTheDocument();
    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('Rules')).toBeInTheDocument();
    expect(screen.getByText('Debug')).toBeInTheDocument();
  });
});
