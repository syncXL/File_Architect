import pathlib
from pathlib import Path
from datetime import datetime
from pydantic import Field
from typing_extensions import Annotated
from langchain_core.tools import tool
from PyQt5.QtWidgets import QApplication, QFileDialog
import sys


@tool
def verify_path(path: Annotated[str, Field(description="The path to be verified")]) -> bool:
    """Verifies if the path is valid"""
    try:
        path = Path(path)
        if path.exists():
            return True
        else:
            return False
    except Exception as err:
        print(f"Error: {err}")
        return False

@tool
def track():
    """Tracks the chat history"""

@tool
def strip(message:Annotated[str, Field(description="Message to be returned after stripping")]) -> str:
    """Strips the previous message starting from the last timee track() function was called"""

@tool
def open_explorer():
    """Opens the file explorer and returns the selected path"""
    app = QApplication(sys.argv)
    folder_path = QFileDialog.getExistingDirectory(None, "Select Folder")
    if folder_path:
        return folder_path
    else:
        return None

# store_root, add_folders, next_folder, make_special, delete_folder, update_folder, next_ufolder, get_structure,create_folder, move, filter_move, delete_path
class FileClass:

    def __init__(self):
        self.root_folders = []
        self.folders = {
            "name" : [],
            "folders" : [],
            "files" : [],
            "path" : [],
            "metadatas" : {
                "Description" : [],
                "special_folder": [],
                "expected_files": [],
                "organized" : []
            }
        }
        self.structure = {
        }
        self.pointer = -1
        self.pointer_root = -1
        self.meta_def = {
            "Description" : "",
            "special_folder" : False,
            "expected_files" : "",
            "organized" : False

        }
    @tool
    def store_root(self, folderpaths: Annotated[list[str], Field(description="A list of full folder paths")]) -> str:
        """Adds the folders to the root folders, they will be explored"""
        for folder in folderpaths:
            self.add_folders(folder)
            self.root_folders.append(folder)
        return "success"

    def add_folder(self, path: Annotated[pathlib.WindowsPath,Field(description="The path of the folder to be added")], **meta) -> str:
        sub_path = list(path.iterdir())
        id = len(self.folders["name"])
        self.folders["name"].append(path.name)
        self.folders["folders"].append([])
        self.folders["files"].append([])
        self.folders["path"].append(path.resolve())
        for meta_keys in list(self.folders["metadatas"].keys()):
            if meta_keys in list(meta.keys()):
                self.folders["metadatas"][meta_keys].append(meta[meta_keys])
            else:
                self.folders["metadatas"][meta_keys].append(self.meta_def[meta_keys])
        return id, sub_path
    @tool
    def add_folders(self,folder):
        """Adds the folders to the root folders, they will be explored"""
        path = Path(folder)
        try: 
            id, sub_path = self.add_folder(path)
        except PermissionError:
            return False
        for sub_path in path.iterdir():
            if sub_path.is_file():
                self.folders["files"][id].append(sub_path.name)
            else:
                success = self.add_folders(sub_path)
                if success:
                    self.folders["folders"][id].append(sub_path.resolve())
        self.structure_root()
        return True
    
    def insert_folder(self, folder: Annotated[pathlib.WindowsPath,Field(description="The path of the folder to be inserted")],
                    parent_path: Annotated[pathlib.WindowsPath,Field(description="The path of the parent folder")],
                    ) -> str:
        """Inserts a folder into the specified parent folder"""
        ind = self.get_ind(parent_path)
        self.folders["folders"][ind].append(folder)
        return "success"

    def get_details(self,folder):
        ind = self.get_ind(folder)
        cols = ["path","folders","files"]
        card = {
            key : self.folders[key][ind]
            for key in cols
        }
        card["metadata"] = {
                    key: (value[ind] if ind < len(value) else "")
                    for key, value in self.folders["metadatas"].items()
                }
        return card

    def make_structure(self, pointer):
        contents = []
        # print(pointer)
        pointer = Path(pointer)
        pointer_details = self.get_details(pointer)
        for child in pointer_details["folders"]:
            child_deets = self.make_structure(child)
            contents.append(child_deets)
        pointer_details["contents"] = contents + pointer_details["files"]
        pointer_details.pop("folders")
        pointer_details.pop("files")
        return pointer_details
    # @tool
    def structure_root(self):
        self.structure = {
            key : self.make_structure(key)
            for key in self.root_folders
        }
        return self.structure
    
    def get_ind(self, folder):
        try:
            ind = self.folders["path"].index(folder)
            return ind
        except ValueError:
            return -1
    @tool
    def make_special(self,folder: Annotated[list[str],Field(description="The path of the folder to be made special")]) -> str:
        """Assigns a folder as special and prunes it's contents"""
        folder = Path(folder)
        ind = self.get_ind(folder)
        if ind != -1:
            self.folders["metadatas"]["special_folder"][ind] = True
            self.prune_tree(ind,root=True)
        else:
            return "not found"
        self.structure_root()
        self.pointer = self.folders["path"][ind -1] if ind < len(self.folders) else -1
        return "success"
    
    def assign_organized(self,folder) -> str:
        ind = self.get_ind(folder)
        if ind != -1:
            self.folders["metadatas"]["organized"][ind] = True
        self.structure_root()
        return "success"

    def prune_tree(self,ind,root=False):
        for folder in self.folders["folders"][ind]:
            sub_ind = self.get_ind(folder)
            if sub_ind != -1:
                self.prune_tree(sub_ind)
        if root:
            self.folders["files"][ind] = []
            self.folders["folders"][ind] = []
        else:
            # self.folderQueue.pop_v(self.folders["path"][ind])
            self.folders["files"].pop(ind)
            self.folders["folders"].pop(ind)
            self.folders["name"].pop(ind)
            self.folders["path"].pop(ind)
    @tool
    def delete_folder(self) -> str:
        """Deletes a folder and all its contents"""
        # for folder in folders:
        Path(self.pointer).rmdir()
        ind = self.get_ind(self.pointer)
        for key in self.folders.keys():
            if key != "metadatas":
                self.folders[key].pop(ind)
            else:
                for meta_key in self.folders["metadatas"].keys():
                    self.folders["metadatas"][meta_key].pop(ind)
        parent_ind = self.get_ind(self.pointer.parent)
        if parent_ind != -1:
            self.folders["folders"][parent_ind].remove(self.pointer.resolve())
        self.pointer = self.folders["path"][ind -1] if ind < len(self.folders) else -1
        self.structure_root()
        return "success"
    @tool
    def create_folder(self,
                    folders: Annotated[list[str],Field(description="The names of the new folders")],
                    descriptions: Annotated[list[str], Field(description="The description of the folder")],
                    expected_file_type: Annotated[list[str],Field(description="Expected type of files to store, e.g .txt, .csv")],
                    ) -> str:
        """Creates a folder in a specific path, it will be organized on default"""
        result = {}
        for folder, description, expected_file in zip(folders, descriptions, expected_file_type):
            try:
                (Path(self.pointer) / folder).mkdir()
                self.add_folder(Path(self.pointer) / folder, Description=description, expected_files=expected_file, organized=True)
                self.insert_folder(Path(self.pointer) / folder, self.pointer)
                result[folder] = "success"
            except Exception as err:
                result[folder] = err
        return self.get_details(self.pointer)
    
    def rm_contents(self, files, folders):
        for inst in files:
            old_p, new_p, file = inst
            old_ind = self.get_ind(old_p)
            new_ind = self.get_ind(new_p)
            self.folders["files"][old_ind].remove(file)
            self.folders["files"][new_ind].append(file)
        for inst in folders:
            old_p, new_p, folder = inst
            old_ind = self.get_ind(old_p)
            new_ind = self.get_ind(new_p)
            self.folders["folders"][old_ind].remove(folder)
            self.folders["folders"][new_ind].append(folder)
    @tool
    def move(self,movepoints: Annotated[
        list[dict], 
        Field(
            description="List of items, each with 'new_path' and 'filenames' properties",
            items={"type": "object", "properties": {
                "filenames": {"type": "list", "description" : "The full filenames to be sent to the new parent path"},
                "new_path": {"type": "string", "description": "Destination of new parent parent path"}
            }}
        )
    ]) -> dict[str,str]:
        """Move files or folders from old path to new path"""
        output = {}
        
        for item in movepoints:
            files = []
            folders = []
            for file in item["filenames"]:
                try:
                    old_path = self.pointer / file
                    new_path = Path(item["new_path"]) / file
                    if old_path.is_file():
                        files.append((old_path.parent,new_path.parent,file))
                    else:
                        folders.append((old_path.parent,new_path.parent,old_path))
                    old_path.rename(new_path)
                    output[file] = "Moved Successfully"
                except Exception as err:
                    print(err)
                    output[file] = f"Failed due to {err}"
            self.rm_contents(files,folders)
        return self.get_details(self.pointer)
    @tool
    def filter_move(self,movepoints: Annotated[
        list[dict], 
        Field(
            description="List of items, each with 'new_parent_path' and 'extension' properties",
            items={"type": "object", "properties": {
                "extension" : {"type": "string", "description" : "The extension of the files to move, e.g '.txt' "},
                "new_parent_path": {"type": "string", "description": "Destination of new parent parent path"}
            }}
        )
    ]) -> dict[str,str]:
        """Move all files with specific extension from old path to new path"""
        output = {}
        for item in movepoints:
            try:
                old_path = self.pointer
                new_path = Path(item["new_parent_path"])
                file_ext = (list(old_path.glob(f"*{item["extension"]}")))
                for file in file_ext:
                    file.rename(new_path/file.name)
                    output[item["extension"]] = f"All {item["extension"]} moved to {new_path}"
                self.rm_contents([(old_path,new_path,file) for file in file_ext],[])
            except Exception as err:
                output[item["extension"]] = f"Failed to move {item} because of {err}"
        return output
    @tool
    def get_next_folder(self) -> str: 
        """Returns the next folder in the queue"""
        if self.pointer == -1:
            self.pointer = self.folders["path"][-1]
        else:
            ind = self.get_ind(self.pointer) -1
            if ind >=0:
                self.pointer = self.folders["path"][ind]
            else:
                self.pointer = -1
                return "0"
        result = self.get_details(self.pointer)
        return result
    @tool
    def get_next_ufolder(self) -> str:
        """Returns the next unorganized folder"""
        while True:
            card = self.get_next_folder()
            if card != "0":
                if (not card["metadata"]["organized"]) | (card == "0"):
                    break
            else:
                break
        return card
    @tool
    def update_folder(self, description: Annotated[str, Field(description="The description of the folder")] = None,
                    expected_files: Annotated[list[str], Field(description="The extension of the files within the folder")] = None,
                    organized: Annotated[str, Field(description="Is the folder organized")] = None) -> str:
        """Updates the folder with the new contents"""
        ind = self.get_ind(self.pointer)
        self.folders["metadatas"]["Description"][ind] = description if description != None else self.folders["metadatas"]["Description"][ind]
        self.folders["metadatas"]["expected_files"][ind] = expected_files if expected_files != None else self.folders["metadatas"]["expected_files"][ind]
        if organized:
            self.assign_organized(self.pointer)
        self.folders["metadatas"]["organized"][ind] = organized if organized != None else self.folders["metadatas"]["organized"][ind]
        return self.get_details(self.pointer)

    def list_folders(self):
        meta_keys = ["Description","special_folder","expected_files","organized"]
        temp = {
            "folder" : self.folders["path"]
        }
        for meta_key in meta_keys:
            temp[meta_key] = self.folders["metadatas"][meta_key]
        return temp
    @tool
    def get_structure(self):
        """Returns the structure of root folders"""
        if self.pointer_root == -1:
            self.pointer_root = self.root_folders[-1]
        else:
            ind = self.root_folders.index(self.pointer_root) -1
            if ind >=0:
                self.pointer_root = self.root_folders[ind]
            else:
                self.pointer_root = -1
                return "0"
        return self.structure[self.pointer_root]

