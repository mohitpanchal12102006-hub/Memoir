import { Navigate, Route, Routes } from 'react-router-dom';
import { Shell } from './components/Shell';
import { Duplicates } from './pages/Duplicates';
import { Review } from './pages/Review';
import { Timeline } from './pages/Timeline';
import { Upload } from './pages/Upload';

export function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Upload />} />
        <Route path="timeline" element={<Timeline />} />
        <Route path="review" element={<Review />} />
        <Route path="duplicates" element={<Duplicates />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
