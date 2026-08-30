import { TProject } from "@/types/project";
import { create } from "zustand";
import { storageService } from "@/lib/storage/storage-service";
import { toast } from "sonner";
import { useMediaStore } from "./media-store";
import { useTimelineStore } from "./timeline-store";
import { generateUUID } from "@/lib/utils";

const normalizeProjectName = (name: string) => name.trim().replace(/\s+/g, " ");

const isSameProjectName = (a: string, b: string) =>
  normalizeProjectName(a).toLowerCase() ===
  normalizeProjectName(b).toLowerCase();

const assertProjectNameAvailable = (
  name: string,
  projects: TProject[],
  currentProjectId?: string
) => {
  const normalizedName = normalizeProjectName(name);
  if (!normalizedName) {
    throw new Error("Project name is required");
  }
  if (/[<>:"/\\|?*]/.test(normalizedName)) {
    throw new Error('Project name cannot contain < > : " / \\ | ? *');
  }
  if (normalizedName === "." || normalizedName === "..") {
    throw new Error("Project name is reserved");
  }

  const duplicate = projects.find(
    (project) =>
      project.id !== currentProjectId &&
      isSameProjectName(project.name, normalizedName)
  );
  if (duplicate) {
    throw new Error("A project with this name already exists");
  }

  return normalizedName;
};

const deleteBackendProjectFiles = async (project: TProject) => {
  const params = new URLSearchParams({ projectName: project.name });
  const response = await fetch(
    `/api/files/project/${encodeURIComponent(project.id)}?${params.toString()}`,
    { method: "DELETE" }
  );
  if (!response.ok) {
    throw new Error(
      await response.text().catch(() => "Failed to delete project files")
    );
  }
};

const renameBackendProjectFiles = async (oldName: string, newName: string) => {
  const response = await fetch("/api/files/project/rename", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      old_project_name: oldName,
      new_project_name: newName,
    }),
  });

  if (!response.ok) {
    throw new Error(
      await response.text().catch(() => "Failed to rename project files")
    );
  }

  return response.json() as Promise<{
    old_dir?: string;
    new_dir?: string;
    moved?: boolean;
  }>;
};

interface ProjectStore {
  activeProject: TProject | null;
  savedProjects: TProject[];
  isLoading: boolean;
  isInitialized: boolean;
  invalidProjectIds?: Set<string>;

  // Actions
  createNewProject: (name: string) => Promise<string>;
  loadProject: (id: string) => Promise<void>;
  saveCurrentProject: () => Promise<void>;
  loadAllProjects: () => Promise<void>;
  deleteProject: (id: string) => Promise<void>;
  closeProject: () => void;
  renameProject: (projectId: string, name: string) => Promise<void>;
  duplicateProject: (projectId: string) => Promise<string>;
  updateProjectBackground: (backgroundColor: string) => Promise<void>;
  updateBackgroundType: (
    type: "color" | "blur",
    options?: { backgroundColor?: string; blurIntensity?: number }
  ) => Promise<void>;
  updateProjectFps: (fps: number) => Promise<void>;

  // Bookmark methods
  toggleBookmark: (time: number) => Promise<void>;
  isBookmarked: (time: number) => boolean;
  removeBookmark: (time: number) => Promise<void>;

  getFilteredAndSortedProjects: (
    searchQuery: string,
    sortOption: string
  ) => TProject[];

  // Global invalid project ID tracking
  isInvalidProjectId: (id: string) => boolean;
  markProjectIdAsInvalid: (id: string) => void;
  clearInvalidProjectIds: () => void;
}

export const useProjectStore = create<ProjectStore>((set, get) => ({
  activeProject: null,
  savedProjects: [],
  isLoading: true,
  isInitialized: false,
  invalidProjectIds: new Set<string>(),

  // Implementation of bookmark methods
  toggleBookmark: async (time: number) => {
    const { activeProject } = get();
    if (!activeProject) return;

    // Round time to the nearest frame
    const fps = activeProject.fps || 30;
    const frameTime = Math.round(time * fps) / fps;

    const bookmarks = activeProject.bookmarks || [];
    let updatedBookmarks: number[];

    // Check if already bookmarked
    const bookmarkIndex = bookmarks.findIndex(
      (bookmark) => Math.abs(bookmark - frameTime) < 0.001
    );

    if (bookmarkIndex !== -1) {
      // Remove bookmark
      updatedBookmarks = bookmarks.filter((_, i) => i !== bookmarkIndex);
    } else {
      // Add bookmark
      updatedBookmarks = [...bookmarks, frameTime].sort((a, b) => a - b);
    }

    const updatedProject = {
      ...activeProject,
      bookmarks: updatedBookmarks,
      updatedAt: new Date(),
    };

    try {
      await storageService.saveProject(updatedProject);
      set({ activeProject: updatedProject });
      await get().loadAllProjects(); // Refresh the list
    } catch (error) {
      console.error("Failed to update project bookmarks:", error);
      toast.error("Failed to update bookmarks", {
        description: "Please try again",
      });
    }
  },

  isBookmarked: (time: number) => {
    const { activeProject } = get();
    if (!activeProject || !activeProject.bookmarks) return false;

    // Round time to the nearest frame
    const fps = activeProject.fps || 30;
    const frameTime = Math.round(time * fps) / fps;

    return activeProject.bookmarks.some(
      (bookmark) => Math.abs(bookmark - frameTime) < 0.001
    );
  },

  removeBookmark: async (time: number) => {
    const { activeProject } = get();
    if (!activeProject || !activeProject.bookmarks) return;

    // Round time to the nearest frame
    const fps = activeProject.fps || 30;
    const frameTime = Math.round(time * fps) / fps;

    const updatedBookmarks = activeProject.bookmarks.filter(
      (bookmark) => Math.abs(bookmark - frameTime) >= 0.001
    );

    if (updatedBookmarks.length === activeProject.bookmarks.length) {
      // No bookmark found to remove
      return;
    }

    const updatedProject = {
      ...activeProject,
      bookmarks: updatedBookmarks,
      updatedAt: new Date(),
    };

    try {
      await storageService.saveProject(updatedProject);
      set({ activeProject: updatedProject });
      await get().loadAllProjects(); // Refresh the list
    } catch (error) {
      console.error("Failed to update project bookmarks:", error);
      toast.error("Failed to remove bookmark", {
        description: "Please try again",
      });
    }
  },

  createNewProject: async (name: string) => {
    const normalizedName = assertProjectNameAvailable(
      name,
      get().savedProjects
    );
    const newProject: TProject = {
      id: generateUUID(),
      name: normalizedName,
      thumbnail: "",
      createdAt: new Date(),
      updatedAt: new Date(),
      backgroundColor: "#000000",
      backgroundType: "color",
      blurIntensity: 8,
      bookmarks: [],
      fps: 30,
    };

    set({ activeProject: newProject });

    try {
      await storageService.saveProject(newProject);
      // Reload all projects to update the list
      await get().loadAllProjects();
      return newProject.id;
    } catch (error) {
      toast.error("Failed to save new project", {
        description:
          error instanceof Error ? error.message : "Please try again",
      });
      throw error;
    }
  },

  loadProject: async (id: string) => {
    if (!get().isInitialized) {
      set({ isLoading: true });
    }

    // Always clear media and timeline first to prevent showing old project data
    const mediaStore = useMediaStore.getState();
    const timelineStore = useTimelineStore.getState();

    // Clear local state immediately
    mediaStore.clearAllMedia();
    timelineStore.clearTimeline();

    // Also clear the active project to ensure clean state
    set({ activeProject: null });

    try {
      const project = await storageService.loadProject(id);
      if (project) {
        set({ activeProject: project });

        // Load project-specific data in parallel
        await Promise.all([
          mediaStore.loadProjectMedia(id),
          timelineStore.loadProjectTimeline(id),
        ]);
      } else {
        throw new Error(`Project with id ${id} not found`);
      }
    } catch (error) {
      console.error("Failed to load project:", error);
      throw error; // Re-throw so the editor page can handle it
    } finally {
      set({ isLoading: false });
    }
  },

  saveCurrentProject: async () => {
    const { activeProject } = get();
    if (!activeProject) return;

    try {
      // Save project metadata and timeline data in parallel
      const timelineStore = useTimelineStore.getState();
      await Promise.all([
        storageService.saveProject(activeProject),
        timelineStore.saveProjectTimeline(activeProject.id),
      ]);
      await get().loadAllProjects(); // Refresh the list
    } catch (error) {
      console.error("Failed to save project:", error);
    }
  },

  loadAllProjects: async () => {
    if (!get().isInitialized) {
      set({ isLoading: true });
    }

    try {
      const projects = await storageService.loadAllProjects();
      set({ savedProjects: projects });
    } catch (error) {
      console.error("Failed to load projects:", error);
    } finally {
      set({ isLoading: false, isInitialized: true });
    }
  },

  deleteProject: async (id: string) => {
    try {
      const projectToDelete =
        get().savedProjects.find((project) => project.id === id) ||
        (await storageService.loadProject(id));

      // Delete project data in parallel
      await Promise.all([
        storageService.deleteProjectMedia(id),
        storageService.deleteProjectTimeline(id),
        storageService.deleteProject(id),
        projectToDelete
          ? deleteBackendProjectFiles(projectToDelete).catch((error) => {
              console.warn("Failed to delete backend project files:", error);
            })
          : Promise.resolve(),
      ]);
      await get().loadAllProjects(); // Refresh the list

      // If we deleted the active project, close it and clear data
      const { activeProject } = get();
      if (activeProject?.id === id) {
        set({ activeProject: null });
        const mediaStore = useMediaStore.getState();
        const timelineStore = useTimelineStore.getState();
        mediaStore.clearAllMedia();
        timelineStore.clearTimeline();
      }
    } catch (error) {
      console.error("Failed to delete project:", error);
    }
  },

  closeProject: () => {
    set({ activeProject: null });

    // Clear data from stores when closing project
    const mediaStore = useMediaStore.getState();
    const timelineStore = useTimelineStore.getState();
    mediaStore.clearAllMedia();
    timelineStore.clearTimeline();
  },

  renameProject: async (id: string, name: string) => {
    const { savedProjects } = get();

    // Find the project to rename
    const projectToRename = savedProjects.find((p) => p.id === id);
    if (!projectToRename) {
      toast.error("Project not found", {
        description: "Please try again",
      });
      return;
    }

    let normalizedName: string;
    try {
      normalizedName = assertProjectNameAvailable(name, savedProjects, id);
    } catch (error) {
      toast.error("Failed to rename project", {
        description:
          error instanceof Error ? error.message : "Please try again",
      });
      throw error;
    }

    const updatedProject = {
      ...projectToRename,
      name: normalizedName,
      updatedAt: new Date(),
    };

    try {
      const renameResult = await renameBackendProjectFiles(
        projectToRename.name,
        normalizedName
      ).catch((error) => {
        console.warn("Failed to rename backend project files:", error);
        return null;
      });

      if (renameResult?.old_dir && renameResult?.new_dir) {
        await storageService.updateProjectMediaServerPathPrefix(
          id,
          renameResult.old_dir,
          renameResult.new_dir
        );
        useMediaStore
          .getState()
          .replaceServerPathPrefix(renameResult.old_dir, renameResult.new_dir);
      }

      // Save to storage
      await storageService.saveProject(updatedProject);

      await get().loadAllProjects();

      // Update activeProject if it's the same project
      const { activeProject } = get();
      if (activeProject?.id === id) {
        set({ activeProject: updatedProject });
      }
    } catch (error) {
      console.error("Failed to rename project:", error);
      toast.error("Failed to rename project", {
        description:
          error instanceof Error ? error.message : "Please try again",
      });
      throw error;
    }
  },

  duplicateProject: async (projectId: string) => {
    try {
      const project = await storageService.loadProject(projectId);
      if (!project) {
        toast.error("Project not found", {
          description: "Please try again",
        });
        throw new Error("Project not found");
      }

      const { savedProjects } = get();

      // Extract the base name (remove any existing numbering)
      const numberMatch = project.name.match(/^\((\d+)\)\s+(.+)$/);
      const baseName = numberMatch ? numberMatch[2] : project.name;
      const existingNumbers: number[] = [];

      // Check for pattern "(number) baseName" in existing projects
      savedProjects.forEach((p) => {
        const match = p.name.match(/^\((\d+)\)\s+(.+)$/);
        if (match && match[2] === baseName) {
          existingNumbers.push(parseInt(match[1], 10));
        }
      });

      const nextNumber =
        existingNumbers.length > 0 ? Math.max(...existingNumbers) + 1 : 1;

      const newProject: TProject = {
        ...project, // Copy all properties from the original project
        id: generateUUID(),
        name: assertProjectNameAvailable(
          `(${nextNumber}) ${baseName}`,
          savedProjects
        ),
        createdAt: new Date(),
        updatedAt: new Date(),
      };

      await storageService.saveProject(newProject);
      await get().loadAllProjects();
      return newProject.id;
    } catch (error) {
      console.error("Failed to duplicate project:", error);
      toast.error("Failed to duplicate project", {
        description:
          error instanceof Error ? error.message : "Please try again",
      });
      throw error;
    }
  },

  updateProjectBackground: async (backgroundColor: string) => {
    const { activeProject } = get();
    if (!activeProject) return;

    const updatedProject = {
      ...activeProject,
      backgroundColor,
      updatedAt: new Date(),
    };

    try {
      await storageService.saveProject(updatedProject);
      set({ activeProject: updatedProject });
      await get().loadAllProjects(); // Refresh the list
    } catch (error) {
      console.error("Failed to update project background:", error);
      toast.error("Failed to update background", {
        description: "Please try again",
      });
    }
  },

  updateBackgroundType: async (
    type: "color" | "blur",
    options?: { backgroundColor?: string; blurIntensity?: number }
  ) => {
    const { activeProject } = get();
    if (!activeProject) return;

    const updatedProject = {
      ...activeProject,
      backgroundType: type,
      ...(options?.backgroundColor && {
        backgroundColor: options.backgroundColor,
      }),
      ...(options?.blurIntensity && { blurIntensity: options.blurIntensity }),
      updatedAt: new Date(),
    };

    try {
      await storageService.saveProject(updatedProject);
      set({ activeProject: updatedProject });
      await get().loadAllProjects(); // Refresh the list
    } catch (error) {
      console.error("Failed to update background type:", error);
      toast.error("Failed to update background", {
        description: "Please try again",
      });
    }
  },

  updateProjectFps: async (fps: number) => {
    const { activeProject } = get();
    if (!activeProject) return;

    const updatedProject = {
      ...activeProject,
      fps,
      updatedAt: new Date(),
    };

    try {
      await storageService.saveProject(updatedProject);
      set({ activeProject: updatedProject });
      await get().loadAllProjects(); // Refresh the list
    } catch (error) {
      console.error("Failed to update project FPS:", error);
      toast.error("Failed to update project FPS", {
        description: "Please try again",
      });
    }
  },

  getFilteredAndSortedProjects: (searchQuery: string, sortOption: string) => {
    const { savedProjects } = get();

    // Filter projects by search query
    const filteredProjects = savedProjects.filter((project) =>
      project.name.toLowerCase().includes(searchQuery.toLowerCase())
    );

    // Sort filtered projects
    const sortedProjects = [...filteredProjects].sort((a, b) => {
      const [key, order] = sortOption.split("-");

      if (key !== "createdAt" && key !== "name") {
        console.warn(`Invalid sort key: ${key}`);
        return 0;
      }

      const aValue = a[key];
      const bValue = b[key];

      if (aValue === undefined || bValue === undefined) return 0;

      if (order === "asc") {
        if (aValue < bValue) return -1;
        if (aValue > bValue) return 1;
        return 0;
      }
      if (aValue > bValue) return -1;
      if (aValue < bValue) return 1;
      return 0;
    });

    return sortedProjects;
  },

  // Global invalid project ID tracking implementation
  isInvalidProjectId: (id: string) => {
    const invalidIds = get().invalidProjectIds || new Set();
    return invalidIds.has(id);
  },

  markProjectIdAsInvalid: (id: string) => {
    set((state) => ({
      invalidProjectIds: new Set([
        ...(state.invalidProjectIds || new Set()),
        id,
      ]),
    }));
  },

  clearInvalidProjectIds: () => {
    set({ invalidProjectIds: new Set() });
  },
}));
